"""Conference submission queue, one-paper worker, and a runnable notebook cell."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import subprocess
import sys
import threading
import zipfile
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import Any
from uuid import uuid4

import paper_audit
import voice
import repro
import shelf
from dataclasses import asdict

from imagine import (
    desk_summary,
    generate_clip,
    motion_prompt,
    parse_imagine,
    render_still,
)
from models import (
    ConferenceProgress,
    DeskClaim,
    PaperProgress,
    ThroughputMetrics,
    deterministic_final,
    is_finding,
)
from batches import (
    LOCAL_PAPERS,
    BatchError,
    PaperLoadError,
    _arxiv_cache,
    _db,
    _events_for_jobs,
    _issues_for_jobs,
    _now,
    arxiv_listings,
    resolve_paper,
)

_IMAGINE_LABEL = "Generated from this desk. Not a finding."

_ARXIV_RE = re.compile(r"(\d{4}\.\d{4,5}|0000\.0000\d)")
# One chair. This is the conference already used for the demo.
DESK_OWNER = "00000000-0000-4000-8000-000000000001"
DEMO_CONFERENCE_ID = "13b04c32-15d0-443b-a087-959b8016f3b8"
_ACTIVE: set[str] = set()
_ACTIVE_LOCK = threading.Lock()


def _columns(conn: Any, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _ensure_desk(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    if "paper_text" not in _columns(conn, "paper_jobs"):
        conn.execute("ALTER TABLE paper_jobs ADD COLUMN paper_text TEXT")
    if "owner" not in _columns(conn, "paper_jobs"):
        conn.execute("ALTER TABLE paper_jobs ADD COLUMN owner TEXT")
    if "owner" not in _columns(conn, "conferences"):
        conn.execute("ALTER TABLE conferences ADD COLUMN owner TEXT")
    if "kaggle_json" not in _columns(conn, "paper_jobs"):
        conn.execute("ALTER TABLE paper_jobs ADD COLUMN kaggle_json TEXT")
    if "listing_title" not in _columns(conn, "paper_jobs"):
        conn.execute("ALTER TABLE paper_jobs ADD COLUMN listing_title TEXT")
    if "abstract" not in _columns(conn, "paper_jobs"):
        conn.execute("ALTER TABLE paper_jobs ADD COLUMN abstract TEXT")
    if "page" not in _columns(conn, "paper_issues"):
        conn.execute("ALTER TABLE paper_issues ADD COLUMN page INTEGER")
    for column, kind in (
        ("claim_id", "TEXT"),
        ("confidence", "REAL"),
        ("depth", "TEXT"),
        ("verdict", "TEXT"),
    ):
        if column not in _columns(conn, "paper_issues"):
            conn.execute(f"ALTER TABLE paper_issues ADD COLUMN {column} {kind}")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS paper_claims (
            claim_id TEXT NOT NULL,
            job_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            text TEXT NOT NULL,
            page INTEGER,
            section TEXT NOT NULL DEFAULT '',
            claim_type TEXT NOT NULL,
            verdict TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0,
            depth TEXT NOT NULL,
            rounds INTEGER NOT NULL DEFAULT 0,
            reason TEXT NOT NULL DEFAULT '',
            evidence_json TEXT NOT NULL DEFAULT '[]',
            catalog_json TEXT,
            computation_json TEXT,
            steps_json TEXT NOT NULL DEFAULT '[]',
            PRIMARY KEY (job_id, claim_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jev_cache (
            cache_key TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            confidence REAL NOT NULL,
            probs_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS catalog_cache (
            cache_key TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS desk_messages (
            message_id TEXT PRIMARY KEY,
            conference_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            role TEXT NOT NULL,
            body TEXT NOT NULL,
            trace_json TEXT NOT NULL,
            quotes_json TEXT NOT NULL,
            papers_json TEXT NOT NULL,
            imagine_json TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    if "imagine_json" not in _columns(conn, "desk_messages"):
        conn.execute("ALTER TABLE desk_messages ADD COLUMN imagine_json TEXT")
    _ensure_one_list(conn)
    conn.commit()


def _hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return f"{salt}${digest.hex()}"


def _password_matches(password: str, stored: str) -> bool:
    salt, digest = stored.split("$", 1)
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
    return hmac.compare_digest(check, digest)


def signup(email: str, password: str) -> dict[str, str]:
    cleaned = email.strip().lower()
    if "@" not in cleaned or len(password) < 8:
        raise BatchError(400, "use an email and a password of at least 8 characters")
    with _db() as conn:
        _ensure_desk(conn)
        existing = conn.execute(
            "SELECT 1 FROM users WHERE email = ?", (cleaned,)
        ).fetchone()
        if existing:
            raise BatchError(400, "an account with that email already exists")
        user_id = str(uuid4())
        conn.execute(
            "INSERT INTO users (user_id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (user_id, cleaned, _hash_password(password), _now()),
        )
        conn.commit()
    return {"user_id": user_id, "email": cleaned}


def login(email: str, password: str) -> dict[str, str]:
    cleaned = email.strip().lower()
    with _db() as conn:
        _ensure_desk(conn)
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (cleaned,)
        ).fetchone()
        if row is None:
            organizer_email = os.environ.get("ORGANIZER_EMAIL", "chair@arxaudit.local").strip().lower()
            organizer_password = os.environ.get("ORGANIZER_PASSWORD", "desk-local")
            if cleaned == organizer_email and password == organizer_password:
                user_id = str(uuid4())
                conn.execute(
                    "INSERT INTO users (user_id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                    (user_id, cleaned, _hash_password(password), _now()),
                )
                conn.commit()
                return {"user_id": user_id, "email": cleaned}
            raise BatchError(400, "that email or password does not match")
        if not _password_matches(password, row["password_hash"]):
            raise BatchError(400, "that email or password does not match")
        return {"user_id": row["user_id"], "email": row["email"]}


_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def link_account(user_id: str, email: str) -> dict[str, str]:
    """Remember a Supabase user so a conference can be owned by that id."""
    cleaned = email.strip().lower()
    if not _UUID_RE.match(user_id) or "@" not in cleaned:
        raise BatchError(400, "a user id and an email are required")
    with _db() as conn:
        _ensure_desk(conn)
        by_id = conn.execute(
            "SELECT email FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if by_id is not None:
            return {"user_id": user_id, "email": by_id["email"]}
        taken = conn.execute(
            "SELECT 1 FROM users WHERE email = ?", (cleaned,)
        ).fetchone()
        if taken is not None:
            raise BatchError(400, "an account with that email already exists")
        conn.execute(
            "INSERT INTO users (user_id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (user_id, cleaned, _hash_password(secrets.token_urlsafe(32)), _now()),
        )
        conn.commit()
    return {"user_id": user_id, "email": cleaned}


def create_user_conference(owner: str, name: str, contact_email: str) -> dict[str, str]:
    if not name.strip() or not contact_email.strip():
        raise BatchError(400, "name and contact email are required")
    with _db() as conn:
        _ensure_desk(conn)
        user = conn.execute("SELECT 1 FROM users WHERE user_id = ?", (owner,)).fetchone()
        if user is None:
            raise BatchError(404, "account not found")
        conference_id = str(uuid4())
        conn.execute(
            """
            INSERT INTO conferences (conference_id, name, contact_email, owner)
            VALUES (?, ?, ?, ?)
            """,
            (conference_id, name.strip(), contact_email.strip(), owner),
        )
        conn.commit()
    return {
        "conference_id": conference_id,
        "name": name.strip(),
        "contact_email": contact_email.strip(),
    }


def parse_arxiv_id(line: str) -> str | None:
    match = _ARXIV_RE.search(line.strip())
    return match.group(1) if match else None


def _ensure_one_list(conn: Any) -> None:
    """Keep the demo conference. Do not touch its papers."""
    row = conn.execute(
        "SELECT owner FROM conferences WHERE conference_id = ?",
        (DEMO_CONFERENCE_ID,),
    ).fetchone()
    if row is None:
        conn.execute(
            """
            INSERT INTO conferences (conference_id, name, contact_email, owner)
            VALUES (?, ?, ?, ?)
            """,
            (DEMO_CONFERENCE_ID, "Sohaib", "chair@arxaudit.local", DESK_OWNER),
        )
    elif row["owner"] != DESK_OWNER:
        conn.execute(
            "UPDATE conferences SET owner = ? WHERE conference_id = ?",
            (DESK_OWNER, DEMO_CONFERENCE_ID),
        )
    conn.commit()


def list_conferences(owner: str | None = None) -> list[dict[str, Any]]:
    with _db() as conn:
        _ensure_desk(conn)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        shelf = ""
        if "author_shelves" in tables:
            shelf = " AND conference_id NOT IN (SELECT conference_id FROM author_shelves)"
        if owner:
            rows = conn.execute(
                f"SELECT * FROM conferences WHERE owner = ?{shelf} ORDER BY name ASC",
                (owner,),
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT * FROM conferences WHERE 1 = 1{shelf} ORDER BY name ASC"
            ).fetchall()
        listed = []
        for row in rows:
            counts = conn.execute(
                """
                SELECT paper_jobs.status, COUNT(*) AS n
                FROM paper_jobs
                JOIN batches ON batches.batch_id = paper_jobs.batch_id
                WHERE batches.conference_id = ?
                GROUP BY paper_jobs.status
                """,
                (row["conference_id"],),
            ).fetchall()
            tally = {item["status"]: item["n"] for item in counts}
            listed.append(
                {
                    "conference_id": row["conference_id"],
                    "name": row["name"],
                    "contact_email": row["contact_email"],
                    "queued": tally.get("queued", 0),
                    "running": tally.get("running", 0),
                    "finished": tally.get("passed", 0)
                    + tally.get("contradicted", 0)
                    + tally.get("error", 0),
                }
            )
        return listed


def add_submissions(
    conference_id: str, lines: list[str], owner: str = "organizer"
) -> dict[str, Any]:
    ids = list(dict.fromkeys(parsed for line in lines if (parsed := parse_arxiv_id(line))))
    if not ids:
        raise BatchError(400, "paste at least one arXiv id")
    with _db() as conn:
        _ensure_desk(conn)
        conference = conn.execute(
            "SELECT 1 FROM conferences WHERE conference_id = ?",
            (conference_id,),
        ).fetchone()
        if conference is None:
            raise BatchError(404, "conference not found")
        rows = conn.execute(
            """
            SELECT paper_jobs.arxiv_id, paper_jobs.listing_title, paper_jobs.job_id
            FROM paper_jobs
            JOIN batches ON batches.batch_id = paper_jobs.batch_id
            WHERE batches.conference_id = ?
            """,
            (conference_id,),
        ).fetchall()
        existing = {row["arxiv_id"] for row in rows}
        blank = {row["arxiv_id"] for row in rows if not (row["listing_title"] or "").strip()}
        by_job = {row["arxiv_id"]: row["job_id"] for row in rows}
    fresh = [arxiv_id for arxiv_id in ids if arxiv_id not in existing]
    stale = [arxiv_id for arxiv_id in ids if arxiv_id in blank]
    if not fresh and not stale:
        open_job_id = next((by_job[arxiv_id] for arxiv_id in ids if arxiv_id in by_job), "")
        return {
            "conference_id": conference_id,
            "added": 0,
            "already": len(ids),
            "arxiv_ids": [],
            "open_job_id": open_job_id,
        }
    listings = arxiv_listings(fresh + stale)
    refreshed = 0
    with _db() as conn:
        _ensure_desk(conn)
        for arxiv_id in stale:
            meta = listings.get(arxiv_id) or {}
            title = (meta.get("title") or "").strip()
            if not title:
                continue
            author = (meta.get("author") or "").strip() or None
            result = conn.execute(
                """
                UPDATE paper_jobs
                SET listing_title = ?, abstract = ?,
                    author_name = CASE
                        WHEN author_name IS NULL OR author_name = '' THEN ?
                        ELSE author_name
                    END
                WHERE arxiv_id = ?
                  AND (listing_title IS NULL OR listing_title = '')
                  AND batch_id IN (
                    SELECT batch_id FROM batches WHERE conference_id = ?
                  )
                """,
                (title, meta.get("abstract") or "", author, arxiv_id, conference_id),
            )
            refreshed += result.rowcount
        if not fresh:
            conn.commit()
            return {
                "conference_id": conference_id,
                "added": 0,
                "refreshed": refreshed,
                "already": len(ids),
                "arxiv_ids": [],
            }
        batch_id = str(uuid4())
        conn.execute(
            """
            INSERT INTO batches (
                batch_id, kind, name, arxiv_ids, conference_id, created_at
            ) VALUES (?, 'batch', 'Your list', ?, ?, ?)
            """,
            (batch_id, json.dumps(fresh), conference_id, _now()),
        )
        position = conn.execute(
            """
            SELECT COALESCE(MAX(paper_jobs.position), -1)
            FROM paper_jobs
            JOIN batches ON batches.batch_id = paper_jobs.batch_id
            WHERE batches.conference_id = ?
            """,
            (conference_id,),
        ).fetchone()[0]
        for arxiv_id in fresh:
            position += 1
            meta = listings.get(arxiv_id) or {}
            author = (meta.get("author") or "").strip() or None
            conn.execute(
                """
                INSERT INTO paper_jobs (
                    job_id, batch_id, arxiv_id, run_id, status, specialist,
                    fitness, issue_count, author_name, author_email,
                    contacted_at, position, owner, listing_title, abstract
                ) VALUES (?, ?, ?, ?, 'queued', NULL, NULL, 0, ?, NULL, NULL, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    batch_id,
                    arxiv_id,
                    str(uuid4()),
                    author,
                    position,
                    owner,
                    meta.get("title") or "",
                    meta.get("abstract") or "",
                ),
            )
        conn.commit()
    return {
        "conference_id": conference_id,
        "added": len(fresh),
        "refreshed": refreshed,
        "already": len(ids) - len(fresh),
        "arxiv_ids": fresh,
    }


def add_upload(
    conference_id: str, data: bytes, owner: str = "organizer"
) -> dict[str, Any]:
    if not data:
        raise BatchError(400, "file is empty")
    if not data.startswith(b"%PDF"):
        raise BatchError(400, "file must be a PDF")
    digest = hashlib.sha256(data).hexdigest()
    arxiv_id = f"upload-{digest[:8]}"
    uploads = _arxiv_cache() / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    dest = uploads / f"{digest}.pdf"
    if not dest.is_file() or dest.stat().st_size == 0:
        dest.write_bytes(data)
    title = "Uploaded paper"
    try:
        text = paper_audit.load_paper(dest)
        for line in text.splitlines():
            cleaned = line.strip()
            if cleaned:
                title = cleaned[:180]
                break
    except Exception:
        title = "Uploaded paper"
    with _db() as conn:
        _ensure_desk(conn)
        conference = conn.execute(
            "SELECT 1 FROM conferences WHERE conference_id = ?",
            (conference_id,),
        ).fetchone()
        if conference is None:
            raise BatchError(404, "conference not found")
        existing = conn.execute(
            """
            SELECT paper_jobs.listing_title
            FROM paper_jobs
            JOIN batches ON batches.batch_id = paper_jobs.batch_id
            WHERE batches.conference_id = ? AND paper_jobs.arxiv_id = ?
            """,
            (conference_id, arxiv_id),
        ).fetchone()
        if existing is not None:
            listed = (existing["listing_title"] or "").strip() or title
            return {
                "conference_id": conference_id,
                "added": 0,
                "arxiv_id": arxiv_id,
                "title": listed,
            }
        batch_id = str(uuid4())
        conn.execute(
            """
            INSERT INTO batches (
                batch_id, kind, name, arxiv_ids, conference_id, created_at
            ) VALUES (?, 'batch', 'Your list', ?, ?, ?)
            """,
            (batch_id, json.dumps([arxiv_id]), conference_id, _now()),
        )
        position = conn.execute(
            """
            SELECT COALESCE(MAX(paper_jobs.position), -1)
            FROM paper_jobs
            JOIN batches ON batches.batch_id = paper_jobs.batch_id
            WHERE batches.conference_id = ?
            """,
            (conference_id,),
        ).fetchone()[0]
        position += 1
        conn.execute(
            """
            INSERT INTO paper_jobs (
                job_id, batch_id, arxiv_id, run_id, status, specialist,
                fitness, issue_count, author_name, author_email,
                contacted_at, position, owner, listing_title, abstract
            ) VALUES (?, ?, ?, ?, 'queued', NULL, NULL, 0, NULL, NULL, NULL, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                batch_id,
                arxiv_id,
                str(uuid4()),
                position,
                owner,
                title,
                "",
            ),
        )
        conn.commit()
    return {
        "conference_id": conference_id,
        "added": 1,
        "arxiv_id": arxiv_id,
        "title": title,
    }


def delete_submission(conference_id: str, job_id: str) -> dict[str, str]:
    with _db() as conn:
        _ensure_desk(conn)
        row = conn.execute(
            """
            SELECT paper_jobs.job_id
            FROM paper_jobs
            JOIN batches ON batches.batch_id = paper_jobs.batch_id
            WHERE paper_jobs.job_id = ? AND batches.conference_id = ?
            """,
            (job_id, conference_id),
        ).fetchone()
        if row is None:
            raise BatchError(404, "paper not found")
        conn.execute("DELETE FROM paper_issues WHERE job_id = ?", (job_id,))
        conn.execute("DELETE FROM paper_claims WHERE job_id = ?", (job_id,))
        conn.execute("DELETE FROM job_events WHERE job_id = ?", (job_id,))
        conn.execute("DELETE FROM paper_jobs WHERE job_id = ?", (job_id,))
        conn.commit()
    return {"deleted": job_id}


def delete_conference(conference_id: str, owner: str | None = None) -> dict[str, str]:
    if conference_id == DEMO_CONFERENCE_ID:
        raise BatchError(409, "this list stays")
    with _ACTIVE_LOCK:
        _ACTIVE.discard(conference_id)
    with _db() as conn:
        _ensure_desk(conn)
        row = conn.execute(
            "SELECT * FROM conferences WHERE conference_id = ?",
            (conference_id,),
        ).fetchone()
        if row is None:
            raise BatchError(404, "conference not found")
        stored = row["owner"] if "owner" in row.keys() else None
        if stored and stored != (owner or ""):
            raise BatchError(404, "conference not found")
        jobs = conn.execute(
            """
            SELECT paper_jobs.job_id
            FROM paper_jobs
            JOIN batches ON batches.batch_id = paper_jobs.batch_id
            WHERE batches.conference_id = ?
            """,
            (conference_id,),
        ).fetchall()
        for job in jobs:
            job_id = job["job_id"]
            conn.execute("DELETE FROM paper_issues WHERE job_id = ?", (job_id,))
            conn.execute("DELETE FROM paper_claims WHERE job_id = ?", (job_id,))
            conn.execute("DELETE FROM job_events WHERE job_id = ?", (job_id,))
        conn.execute(
            """
            DELETE FROM paper_jobs
            WHERE batch_id IN (SELECT batch_id FROM batches WHERE conference_id = ?)
            """,
            (conference_id,),
        )
        conn.execute("DELETE FROM batches WHERE conference_id = ?", (conference_id,))
        conn.execute("DELETE FROM desk_messages WHERE conference_id = ?", (conference_id,))
        conn.execute("DELETE FROM conferences WHERE conference_id = ?", (conference_id,))
        conn.commit()
    return {"deleted": conference_id}


def reread_paper(job_id: str) -> dict[str, str]:
    with _db() as conn:
        _ensure_desk(conn)
        row = conn.execute(
            "SELECT job_id, status FROM paper_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            raise BatchError(404, "paper not found")
        if row["status"] == "running":
            raise BatchError(409, "this paper is already being read")
        conn.execute("DELETE FROM paper_issues WHERE job_id = ?", (job_id,))
        conn.execute("DELETE FROM paper_claims WHERE job_id = ?", (job_id,))
        conn.execute("DELETE FROM job_events WHERE job_id = ?", (job_id,))
        conn.execute(
            """
            UPDATE paper_jobs
            SET status = 'queued', specialist = NULL, issue_count = 0, fitness = NULL
            WHERE job_id = ?
            """,
            (job_id,),
        )
        conn.commit()
    threading.Thread(
        target=_audit_job,
        args=(job_id,),
        daemon=True,
        name=f"reread-{job_id[:8]}",
    ).start()
    return {"job_id": job_id, "status": "queued"}


def start_run(conference_id: str, cap: int | None) -> dict[str, Any]:
    if cap is not None and cap < 1:
        raise BatchError(400, "cap must be at least 1")
    with _ACTIVE_LOCK:
        if conference_id in _ACTIVE:
            return {"started": False, "running": True}
        _ACTIVE.add(conference_id)
    threading.Thread(
        target=_drain,
        args=(conference_id, cap),
        daemon=True,
        name=f"desk-{conference_id[:8]}",
    ).start()
    return {"started": True, "running": True, "cap": cap}


def _desk_workers() -> int:
    raw = os.environ.get("DESK_WORKERS", "2")
    try:
        count = int(raw)
    except ValueError:
        count = 2
    return max(1, min(8, count))


def _drain(conference_id: str, cap: int | None) -> None:
    try:
        workers = _desk_workers()
        with _db() as conn:
            _ensure_desk(conn)
            query = """
                SELECT paper_jobs.job_id
                FROM paper_jobs
                JOIN batches ON batches.batch_id = paper_jobs.batch_id
                WHERE batches.conference_id = ? AND paper_jobs.status = 'queued'
                ORDER BY paper_jobs.position ASC
            """
            params: list[Any] = [conference_id]
            if cap is not None:
                query += " LIMIT ?"
                params.append(cap)
            job_ids = [row["job_id"] for row in conn.execute(query, params)]
        next_index = 0
        pending: dict[Any, str] = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            while next_index < len(job_ids) or pending:
                with _ACTIVE_LOCK:
                    if conference_id not in _ACTIVE:
                        break
                while len(pending) < workers and next_index < len(job_ids):
                    with _ACTIVE_LOCK:
                        if conference_id not in _ACTIVE:
                            break
                    job_id = job_ids[next_index]
                    next_index += 1
                    future = pool.submit(_audit_job, job_id)
                    pending[future] = job_id
                if not pending:
                    break
                done, _ = wait(set(pending), timeout=0.05, return_when=FIRST_COMPLETED)
                for future in done:
                    pending.pop(future, None)
                    future.result()
    finally:
        with _ACTIVE_LOCK:
            _ACTIVE.discard(conference_id)


def _audit_job(job_id: str) -> None:
    with _db() as conn:
        _ensure_desk(conn)
        row = conn.execute(
            "SELECT * FROM paper_jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row is None or row["status"] != "queued":
            return
        conn.execute(
            "UPDATE paper_jobs SET status = 'running', specialist = 'ingest' WHERE job_id = ?",
            (job_id,),
        )
        conn.commit()
        arxiv_id = row["arxiv_id"]

    try:
        path, author_name = resolve_paper(arxiv_id)
    except PaperLoadError as exc:
        _finish_error(job_id, str(exc))
        return

    text = paper_audit.load_paper(path)

    def recorder(recorded_job: str, specialist: str, state: str, detail: str) -> None:
        with _db() as conn:
            conn.execute(
                """
                INSERT INTO job_events (
                    event_id, job_id, specialist, state, detail, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(uuid4()), recorded_job, specialist, state, detail, _now()),
            )
            if state == "started":
                conn.execute(
                    "UPDATE paper_jobs SET specialist = ? WHERE job_id = ?",
                    (specialist, recorded_job),
                )
            conn.commit()

    result = paper_audit.audit_paper(
        path, job_id, recorder=recorder, repro=repro.reproduce
    )
    issues = list(result.get("issues") or [])
    claims = list(result.get("claims") or [])
    findings = [claim for claim in claims if is_finding(claim)]
    status = "contradicted" if issues or findings else "passed"
    with _db() as conn:
        for issue in issues:
            _insert_issue(conn, job_id, issue)
        _persist_claims(conn, job_id, claims)
        conn.execute(
            """
            UPDATE paper_jobs
            SET status = ?, specialist = 'stamp', fitness = ?, issue_count = ?,
                author_name = ?, paper_text = ?, kaggle_json = ?
            WHERE job_id = ?
            """,
            (
                status,
                0.0 if issues or findings else 1.0,
                len(issues),
                author_name,
                text,
                json.dumps(result.get("kaggle") or {}),
                job_id,
            ),
        )
        conn.commit()


def _insert_issue(conn: Any, job_id: str, issue: dict[str, Any]) -> None:
    page = issue.get("page")
    conn.execute(
        """
        INSERT INTO paper_issues (
            job_id, issue_type, claim_text, evidence_span, jev_label, reason, page,
            claim_id, confidence, depth, verdict
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            issue["issue_type"],
            issue["claim_text"],
            issue["evidence_span"],
            issue["jev_label"],
            issue["reason"],
            page if isinstance(page, int) else None,
            issue.get("claim_id"),
            issue.get("confidence"),
            issue.get("depth"),
            issue.get("verdict"),
        ),
    )


def _persist_claims(conn: Any, job_id: str, claims: list[dict[str, Any]]) -> None:
    conn.execute("DELETE FROM paper_claims WHERE job_id = ?", (job_id,))
    for position, raw in enumerate(claims):
        payload = {key: value for key, value in raw.items() if not str(key).startswith("_")}
        claim = DeskClaim.model_validate({**payload, "job_id": job_id})
        conn.execute(
            """
            INSERT INTO paper_claims (
                claim_id, job_id, position, text, page, section, claim_type, verdict,
                confidence, depth, rounds, reason, evidence_json, catalog_json,
                computation_json, steps_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                claim.claim_id,
                job_id,
                position,
                claim.text,
                claim.page,
                claim.section,
                str(claim.claim_type),
                str(claim.verdict),
                claim.confidence,
                str(claim.depth),
                claim.rounds,
                claim.reason,
                json.dumps([item.model_dump(mode="json") for item in claim.evidence]),
                json.dumps(claim.catalog.model_dump(mode="json")) if claim.catalog else None,
                json.dumps(claim.computation.model_dump(mode="json"))
                if claim.computation
                else None,
                json.dumps(claim.steps),
            ),
        )


def _claims_for_job(conn: Any, job_id: str) -> list[dict[str, Any]]:
    try:
        rows = conn.execute(
            "SELECT * FROM paper_claims WHERE job_id = ? ORDER BY position ASC",
            (job_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    claims: list[dict[str, Any]] = []
    for row in rows:
        claims.append(
            {
                "claim_id": row["claim_id"],
                "job_id": row["job_id"],
                "text": row["text"],
                "page": row["page"],
                "section": row["section"],
                "claim_type": row["claim_type"],
                "verdict": row["verdict"],
                "confidence": row["confidence"],
                "depth": row["depth"],
                "rounds": row["rounds"],
                "reason": row["reason"],
                "evidence": json.loads(row["evidence_json"] or "[]"),
                "steps": json.loads(row["steps_json"] or "[]"),
                "catalog": json.loads(row["catalog_json"]) if row["catalog_json"] else None,
                "computation": json.loads(row["computation_json"])
                if row["computation_json"]
                else None,
            }
        )
    return claims


def _empty_summary() -> dict[str, Any]:
    return {
        "analyzed": 0,
        "supported": 0,
        "contradicted": 0,
        "unresolved": 0,
        "not_reproduced": 0,
        "insufficient": 0,
        "not_checked": 0,
        "categories": {
            "citations": {"resolved": 0, "total": 0, "not_checked": 0},
            "internal": {"supported": 0, "total": 0, "not_checked": 0},
            "numerical": {"consistent": 0, "total": 0, "not_checked": 0},
            "computational": {"reproduced": 0, "total": 0, "not_checked": 0},
        },
    }


def summarize_claims(claims: list[dict[str, Any]]) -> dict[str, Any]:
    summary = _empty_summary()
    categories = summary["categories"]
    for claim in claims:
        verdict = str(claim.get("verdict") or "")
        kind = str(claim.get("claim_type") or "")
        summary["analyzed"] += 1
        if verdict in ("supported", "reproduced"):
            summary["supported"] += 1
        elif verdict == "contradicted":
            summary["contradicted"] += 1
        elif verdict == "unresolved":
            summary["unresolved"] += 1
        elif verdict == "could_not_reproduce":
            summary["not_reproduced"] += 1
        elif verdict == "insufficient_evidence":
            summary["insufficient"] += 1
        elif verdict in ("not_checked", "not_mentioned", "ambiguous"):
            summary["not_checked"] += 1
        if kind == "citation":
            categories["citations"]["total"] += 1
            if verdict == "supported":
                categories["citations"]["resolved"] += 1
            if verdict in ("not_checked", "not_mentioned", "ambiguous"):
                categories["citations"]["not_checked"] += 1
        elif kind == "semantic":
            categories["internal"]["total"] += 1
            if verdict == "supported":
                categories["internal"]["supported"] += 1
            if verdict in ("not_checked", "not_mentioned", "ambiguous"):
                categories["internal"]["not_checked"] += 1
        elif kind in ("numerical", "numerical_comparison"):
            categories["numerical"]["total"] += 1
            if verdict == "supported":
                categories["numerical"]["consistent"] += 1
            if verdict in ("not_checked", "not_mentioned", "ambiguous"):
                categories["numerical"]["not_checked"] += 1
        elif kind == "dataset":
            categories["computational"]["total"] += 1
            if verdict == "reproduced":
                categories["computational"]["reproduced"] += 1
            if verdict in ("not_checked", "not_mentioned", "ambiguous"):
                categories["computational"]["not_checked"] += 1
    return summary


def finding_count(claims: list[dict[str, Any]], issues: list[dict[str, Any]]) -> int:
    if claims:
        return sum(1 for claim in claims if is_finding(claim))
    return len(issues)


def _finish_error(job_id: str, detail: str) -> None:
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO job_events (
                event_id, job_id, specialist, state, detail, created_at
            ) VALUES (?, ?, 'ingest', 'failed', ?, ?)
            """,
            (str(uuid4()), job_id, detail, _now()),
        )
        conn.execute(
            """
            UPDATE paper_jobs
            SET status = 'error', specialist = NULL, issue_count = 0
            WHERE job_id = ?
            """,
            (job_id,),
        )
        conn.commit()



_CHECK_SPECIALISTS = frozenset(
    {"evidence", "citations", "numbers", "tables", "dataset"}
)
_DONE_STATUSES = frozenset({"passed", "contradicted", "error"})
_SETTLED_VERDICTS = frozenset(
    {
        "supported",
        "contradicted",
        "unresolved",
        "reproduced",
        "could_not_reproduce",
        "insufficient_evidence",
        "not_mentioned",
        "ambiguous",
    }
)


def _events_for_job(conn: Any, job_id: str) -> list[Any]:
    return _events_for_jobs(conn, [job_id])


def _event_finished(events: list[Any], specialist: str) -> bool:
    return any(row["specialist"] == specialist and row["state"] == "finished" for row in events)


def _event_started(events: list[Any], specialist: str) -> bool:
    return any(row["specialist"] == specialist and row["state"] == "started" for row in events)


def _claim_steps(claim: dict[str, Any]) -> list[str]:
    return [str(step) for step in (claim.get("steps") or [])]


def _claims_done(claims: list[dict[str, Any]]) -> int:
    done = 0
    for claim in claims:
        verdict = str(claim.get("verdict") or "")
        if verdict in _SETTLED_VERDICTS or deterministic_final(claim):
            done += 1
    return done


def _lya_done_count(claims: list[dict[str, Any]]) -> int:
    return sum(1 for claim in claims if "Lya verdict" in _claim_steps(claim))


def _jev_running_count(claims: list[dict[str, Any]], *, specialist: str) -> int:
    if specialist != "verify":
        return 0
    running = 0
    for claim in claims:
        steps = _claim_steps(claim)
        if any(step.startswith("Jev requested") for step in steps) and "Jev judgment" not in steps:
            running += 1
    return running


def _paper_phase(
    *,
    status: str,
    specialist: str,
    claims: list[dict[str, Any]],
    events: list[Any],
) -> str:
    if status in _DONE_STATUSES:
        return "done"
    if not _event_finished(events, "claims"):
        return "parse"
    if not all(_event_finished(events, name) for name in _CHECK_SPECIALISTS):
        return "checks"
    if not _event_started(events, "verify"):
        return "checks"
    if _jev_running_count(claims, specialist=specialist) > 0:
        return "jev"
    pending_lya = any(
        str(claim.get("claim_type") or "") in {"numerical", "numerical_comparison", "semantic"}
        and not deterministic_final(claim)
        and "Lya verdict" not in _claim_steps(claim)
        and "Jev judgment" not in _claim_steps(claim)
        for claim in claims
    )
    if pending_lya or specialist == "verify":
        return "lya"
    return "checks"


def paper_progress(conn: Any, job: Any, claims: list[dict[str, Any]]) -> dict[str, Any]:
    events = _events_for_job(conn, job["job_id"])
    status = str(job["status"] or "")
    specialist = str(job["specialist"] or "")
    parsed = _event_finished(events, "claims") or bool(claims)
    progress = PaperProgress(
        parsed=parsed,
        claims_total=len(claims),
        claims_done=_claims_done(claims),
        findings_so_far=sum(1 for claim in claims if is_finding(claim)),
        lya_done=_lya_done_count(claims),
        jev_running=_jev_running_count(claims, specialist=specialist),
        phase=_paper_phase(
            status=status,
            specialist=specialist,
            claims=claims,
            events=events,
        ),
    )
    return asdict(progress)


def conference_progress(conn: Any, jobs: list[Any]) -> dict[str, Any]:
    papers_total = len(jobs)
    papers_done = 0
    papers_with_findings = 0
    papers_running = 0
    papers_queued = 0
    for job in jobs:
        status = str(job["status"] or "")
        if status in _DONE_STATUSES:
            papers_done += 1
            claims = _claims_for_job(conn, job["job_id"])
            issues = _issues_for_jobs(conn, [job["job_id"]])
            if finding_count(claims, issues) > 0 or int(job["issue_count"] or 0) > 0:
                papers_with_findings += 1
        elif status == "running":
            papers_running += 1
            claims = _claims_for_job(conn, job["job_id"])
            if any(is_finding(claim) for claim in claims):
                papers_with_findings += 1
        elif status == "queued":
            papers_queued += 1
    progress = ConferenceProgress(
        papers_total=papers_total,
        papers_done=papers_done,
        papers_with_findings=papers_with_findings,
        papers_running=papers_running,
        papers_queued=papers_queued,
    )
    return asdict(progress)


def _parse_ts(value: str | None) -> float | None:
    if not value:
        return None
    from datetime import datetime

    cleaned = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(cleaned).timestamp()
    except ValueError:
        return None


def _conference_job_ids(conn: Any, conference_id: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT paper_jobs.job_id
        FROM paper_jobs
        JOIN batches ON batches.batch_id = paper_jobs.batch_id
        WHERE batches.conference_id = ?
        ORDER BY paper_jobs.position ASC
        """,
        (conference_id,),
    ).fetchall()
    return [str(row["job_id"]) for row in rows]


def _metrics_from_claim_row(row: Any) -> tuple[int, int, int, int | None]:
    comp = json.loads(row["computation_json"]) if row["computation_json"] else None
    steps = json.loads(row["steps_json"] or "[]")
    step_text = [str(step) for step in steps]
    payload = {"verdict": row["verdict"], "steps": step_text, "computation": comp}
    if deterministic_final(payload):
        return 1, 0, 0, None
    if "Jev judgment" in step_text:
        return 0, 0, 1, int(row["rounds"] or 0)
    if "Lya verdict" in step_text:
        return 0, 1, 0, None
    return 0, 0, 0, None


def conference_metrics(conference_id: str) -> dict[str, Any]:
    with _db() as conn:
        _ensure_desk(conn)
        row = conn.execute(
            "SELECT conference_id FROM conferences WHERE conference_id = ?",
            (conference_id,),
        ).fetchone()
        if row is None:
            raise BatchError(404, "conference not found")
        job_ids = _conference_job_ids(conn, conference_id)
        papers = len(job_ids)
        if not job_ids:
            return asdict(
                ThroughputMetrics(
                    conference_id=conference_id,
                    papers=0,
                    claims=0,
                    resolved_deterministic=0,
                    resolved_lya=0,
                    escalated_jev=0,
                    avg_jev_rounds=0,
                    citation_cache_hits=0,
                    citation_cache_misses=0,
                    paper_cache_hits=0,
                    paper_cache_misses=0,
                    lya_batches=0,
                    claims_per_lya_batch=0,
                    time_to_first_finding_ms=None,
                    median_paper_ms=None,
                )
            )

        placeholders = ",".join("?" for _ in job_ids)
        claim_rows = conn.execute(
            f"SELECT steps_json, rounds, verdict, computation_json FROM paper_claims WHERE job_id IN ({placeholders})",
            job_ids,
        ).fetchall()
        claims = len(claim_rows)
        resolved_deterministic = 0
        resolved_lya = 0
        escalated_jev = 0
        jev_rounds: list[int] = []
        for row in claim_rows:
            det, lya, jev, rounds = _metrics_from_claim_row(row)
            resolved_deterministic += det
            resolved_lya += lya
            escalated_jev += jev
            if rounds is not None:
                jev_rounds.append(rounds)
        avg_jev_rounds = sum(jev_rounds) / len(jev_rounds) if jev_rounds else 0

        citation_cache_hits = 0
        citation_cache_misses = 0
        paper_cache_hits = 0
        paper_cache_misses = 0

        lya_batches = sum(
            1
            for event in conn.execute(
                f"""
                SELECT job_events.detail
                FROM job_events
                JOIN paper_jobs ON paper_jobs.job_id = job_events.job_id
                JOIN batches ON batches.batch_id = paper_jobs.batch_id
                WHERE batches.conference_id = ? AND job_events.specialist = 'verify'
                """,
                (conference_id,),
            ).fetchall()
            if event["detail"]
        )

        claims_per_lya_batch = 0
        if lya_batches:
            claims_per_lya_batch = resolved_lya / lya_batches if resolved_lya else 0

        event_rows = conn.execute(
            """
            SELECT job_events.created_at, job_events.job_id, paper_jobs.status
            FROM job_events
            JOIN paper_jobs ON paper_jobs.job_id = job_events.job_id
            JOIN batches ON batches.batch_id = paper_jobs.batch_id
            WHERE batches.conference_id = ?
            ORDER BY job_events.created_at ASC
            """,
            (conference_id,),
        ).fetchall()
        run_start: float | None = None
        for event in event_rows:
            ts = _parse_ts(event["created_at"])
            if ts is not None:
                run_start = ts if run_start is None else min(run_start, ts)

        first_finding_ms: int | None = None
        if run_start is not None:
            for row in claim_rows:
                steps = json.loads(row["steps_json"] or "[]")
                comp = json.loads(row["computation_json"]) if row["computation_json"] else None
                payload = {
                    "verdict": row["verdict"],
                    "steps": [str(step) for step in steps],
                    "computation": comp,
                    "confidence": 0,
                    "claim_type": "numerical",
                }
                if is_finding(payload):
                    first_finding_ms = 0
                    break

        finished_ms: list[int] = []
        per_job_start: dict[str, float] = {}
        per_job_end: dict[str, float] = {}
        for event in event_rows:
            job_id = str(event["job_id"])
            ts = _parse_ts(event["created_at"])
            if ts is None:
                continue
            per_job_start.setdefault(job_id, ts)
            per_job_end[job_id] = ts
        for job_id in job_ids:
            start = per_job_start.get(job_id)
            end = per_job_end.get(job_id)
            status_row = conn.execute(
                "SELECT status FROM paper_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if start is not None and end is not None and status_row and status_row["status"] in _DONE_STATUSES:
                finished_ms.append(max(0, int((end - start) * 1000)))
        median_paper_ms = None
        if finished_ms:
            ordered = sorted(finished_ms)
            median_paper_ms = ordered[len(ordered) // 2]

        return asdict(
            ThroughputMetrics(
                conference_id=conference_id,
                papers=papers,
                claims=claims,
                resolved_deterministic=resolved_deterministic,
                resolved_lya=resolved_lya,
                escalated_jev=escalated_jev,
                avg_jev_rounds=avg_jev_rounds,
                citation_cache_hits=citation_cache_hits,
                citation_cache_misses=citation_cache_misses,
                paper_cache_hits=paper_cache_hits,
                paper_cache_misses=paper_cache_misses,
                lya_batches=lya_batches,
                claims_per_lya_batch=claims_per_lya_batch,
                time_to_first_finding_ms=first_finding_ms,
                median_paper_ms=median_paper_ms,
            )
        )


def conference_desk(conference_id: str) -> dict[str, Any]:
    with _db() as conn:
        _ensure_desk(conn)
        row = conn.execute(
            "SELECT * FROM conferences WHERE conference_id = ?",
            (conference_id,),
        ).fetchone()
        if row is None:
            raise BatchError(404, "conference not found")
        jobs = conn.execute(
            """
            SELECT paper_jobs.*
            FROM paper_jobs
            JOIN batches ON batches.batch_id = paper_jobs.batch_id
            WHERE batches.conference_id = ?
            ORDER BY paper_jobs.position ASC
            """,
            (conference_id,),
        ).fetchall()
        return {
            "conference_id": row["conference_id"],
            "name": row["name"],
            "contact_email": row["contact_email"],
            "running": conference_id in _ACTIVE,
            "progress": conference_progress(conn, jobs),
            "papers": [_paper_dict(conn, job) for job in jobs],
        }


def paper_desk(job_id: str) -> dict[str, Any]:
    with _db() as conn:
        _ensure_desk(conn)
        job = conn.execute(
            "SELECT * FROM paper_jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if job is None:
            raise BatchError(404, "paper not found")
        paper = _paper_dict(conn, job)
    abstract = str((paper.get("sections") or {}).get("abstract") or "").strip()
    source = abstract or str(paper.get("paper_text") or "").strip()
    paper["neighbors"] = shelf.nearest_abstracts(source) if source else []
    return paper


_FIXTURE_TITLES = {
    "0000.00001": "Reported Accuracy on a Public Benchmark",
    "0000.00002": "Measured Accuracy on a Public Benchmark",
    "0000.00003": "Adaptive Reasoning Systems",
}


def paper_title(arxiv_id: str, text: str) -> str:
    for line in (text or "").splitlines():
        cleaned = line.strip()
        if cleaned:
            return cleaned[:180]
    return _FIXTURE_TITLES.get(arxiv_id, "")


def _paper_dict(conn: Any, job: Any) -> dict[str, Any]:
    text = job["paper_text"] or ""
    sections = paper_audit.split_sections(text) if text else {}
    kaggle = None
    raw = job["kaggle_json"] if "kaggle_json" in job.keys() else ""
    if raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict) and parsed:
            kaggle = parsed
    keys = set(job.keys())
    listing = (job["listing_title"] or "").strip() if "listing_title" in keys else ""
    abstract = (job["abstract"] or "").strip() if "abstract" in keys else ""
    if not abstract and sections:
        abstract = (sections.get("abstract") or "").strip()
    issues = paper_audit.unique_issues(_issues_for_jobs(conn, [job["job_id"]]))
    claims = _claims_for_job(conn, job["job_id"])
    return {
        "job_id": job["job_id"],
        "arxiv_id": job["arxiv_id"],
        "title": listing or paper_title(job["arxiv_id"], text),
        "abstract": abstract,
        "status": job["status"],
        "specialist": job["specialist"],
        "author_name": job["author_name"],
        "issue_count": job["issue_count"],
        "finding_count": finding_count(claims, issues),
        "paper_text": text,
        "sections": {key: sections.get(key, "") for key in paper_audit.SECTION_KEYS}
        if text
        else {},
        "issues": issues,
        "claims": claims,
        "summary": summarize_claims(claims),
        "events": _events_for_jobs(conn, [job["job_id"]]),
        "kaggle": kaggle,
        "progress": paper_progress(conn, job, claims),
    }


def known_fixture(arxiv_id: str) -> bool:
    return arxiv_id in LOCAL_PAPERS


_JUDGED = {"passed", "contradicted", "error"}
_CHECK_LABELS = {
    "citation": "Citations",
    "number": "Numbers",
    "support": "Support",
    "dataset": "Named datasets",
    "test": "Rerun",
}


def _conference_name_for_job(job_id: str) -> str:
    with _db() as conn:
        _ensure_desk(conn)
        row = conn.execute(
            """
            SELECT conferences.name
            FROM paper_jobs
            JOIN batches ON batches.batch_id = paper_jobs.batch_id
            JOIN conferences ON conferences.conference_id = batches.conference_id
            WHERE paper_jobs.job_id = ?
            """,
            (job_id,),
        ).fetchone()
    return str(row["name"]) if row else ""


def _finding_sentence(issues: list[dict[str, Any]]) -> str:
    reasons: list[str] = []
    seen: set[str] = set()
    for item in issues:
        if item.get("issue_type") == "ai_likeness":
            continue
        reason = " ".join(str(item.get("reason") or "").split())
        if not reason:
            continue
        if not reason.endswith("."):
            reason = f"{reason}."
        key = reason.lower()
        if key in seen:
            continue
        seen.add(key)
        reasons.append(reason)
    return " ".join(reasons)


_CLAIM_VERDICT_WORD = {
    "supported": "Supported",
    "contradicted": "Contradicted",
    "not_mentioned": "Not found",
    "unresolved": "Unresolved",
    "ambiguous": "Ambiguous",
    "reproduced": "Reproduced",
    "could_not_reproduce": "Could not reproduce",
    "insufficient_evidence": "Insufficient evidence",
    "not_checked": "Not checked",
}

_CATALOG_NAME = {
    "crossref": "Crossref",
    "openalex": "OpenAlex",
    "semantic_scholar": "Semantic Scholar",
}


def _legend_line(summary: dict[str, Any]) -> str:
    return " · ".join(
        [
            f"{int(summary.get('supported') or 0)} supported",
            f"{int(summary.get('contradicted') or 0)} contradicted",
            f"{int(summary.get('unresolved') or 0)} unresolved",
            f"{int(summary.get('insufficient') or 0)} needs review",
            f"{int(summary.get('not_checked') or 0)} not checked",
        ]
    )


def _summary_line(summary: dict[str, Any]) -> str:
    analyzed = int(summary.get("analyzed") or 0)
    if analyzed <= 0:
        return ""
    noun = "claim analyzed" if analyzed == 1 else "claims analyzed"
    parts = [f"{analyzed} {noun}", f"{int(summary.get('supported') or 0)} supported"]
    contradicted = int(summary.get("contradicted") or 0)
    if contradicted:
        parts.append(f"{contradicted} contradicted")
    unresolved = int(summary.get("unresolved") or 0)
    if unresolved:
        label = "unresolved citation" if unresolved == 1 else "unresolved citations"
        parts.append(f"{unresolved} {label}")
    not_reproduced = int(summary.get("not_reproduced") or 0)
    if not_reproduced:
        parts.append(f"{not_reproduced} not reproduced")
    insufficient = int(summary.get("insufficient") or 0)
    if insufficient:
        label = "needs human review" if insufficient == 1 else "need human review"
        parts.append(f"{insufficient} {label}")
    return " · ".join(parts)


def _category_lines(summary: dict[str, Any]) -> list[str]:
    categories = summary.get("categories") or {}
    rows = [
        ("Citations resolved", categories.get("citations") or {}, "resolved"),
        ("Internal consistency", categories.get("internal") or {}, "supported"),
        ("Numerical consistency", categories.get("numerical") or {}, "consistent"),
        ("Computational reproduction", categories.get("computational") or {}, "reproduced"),
    ]
    lines: list[str] = []
    for label, bucket, key in rows:
        total = int(bucket.get("total") or 0)
        if total <= 0:
            continue
        shown = f"{label} {int(bucket.get(key) or 0)} / {total}"
        unchecked = int(bucket.get("not_checked") or 0)
        if unchecked:
            shown += f" · {unchecked} not checked"
        lines.append(shown)
    return lines


def _primary_evidence(claim: dict[str, Any]) -> dict[str, Any] | None:
    evidence = list(claim.get("evidence") or [])
    for item in evidence:
        if item.get("role") == "contradicts" and str(item.get("text") or "").strip():
            return item
    for item in evidence:
        if str(item.get("text") or "").strip():
            return item
    return None


def _append_finding_section(lines: list[str], claim: dict[str, Any]) -> None:
    text = str(claim.get("text") or "").strip()
    lines.extend(["", f"## {text or 'Finding'}", ""])
    if text:
        lines.append(text)
    page = claim.get("page")
    if isinstance(page, int) and page >= 1:
        lines.append(f"Claim page: {page}")
    evidence = _primary_evidence(claim)
    if evidence is not None:
        evidence_page = evidence.get("page")
        if isinstance(evidence_page, int) and evidence_page >= 1:
            lines.append(f"Evidence page: {evidence_page}")
        quote = str(evidence.get("text") or "").strip()
        if quote:
            lines.append(f"> {quote}")
    verdict = str(claim.get("verdict") or "")
    lines.append(_CLAIM_VERDICT_WORD.get(verdict, verdict or "Not checked"))
    confidence = float(claim.get("confidence") or 0.0)
    lines.append(f"Confidence: {int(round(confidence * 100))}%")
    catalog = claim.get("catalog") if isinstance(claim.get("catalog"), dict) else None
    queried = list((catalog or {}).get("queried") or []) if catalog else []
    for row in queried:
        name = str(row.get("catalog") or "").strip()
        label = _CATALOG_NAME.get(name, name or "Catalog")
        status = str(row.get("status") or "").strip() or "not_checked"
        lines.append(f"{label}: {status}")
    computation = claim.get("computation") if isinstance(claim.get("computation"), dict) else None
    if computation:
        expected = computation.get("expected")
        actual = computation.get("actual")
        formula = str(computation.get("formula") or "").strip()
        parts = []
        if expected is not None:
            parts.append(f"expected {expected}")
        if actual is not None:
            parts.append(f"actual {actual}")
        if formula:
            parts.append(f"formula {formula}")
        if parts:
            lines.append("; ".join(parts))
    for step in claim.get("steps") or []:
        cleaned = str(step or "").strip()
        if cleaned:
            lines.append(cleaned)


def _append_issue_sections(lines: list[str], issues: list[dict[str, Any]]) -> None:
    failed = [item for item in issues if item.get("issue_type") != "ai_likeness"]
    for item in failed:
        kind = _CHECK_LABELS.get(
            str(item.get("issue_type") or ""),
            str(item.get("issue_type") or "Check"),
        )
        lines.extend(["", f"## {kind}", ""])
        claim = str(item.get("claim_text") or "").strip()
        if claim:
            lines.append(claim)
        page = item.get("page")
        if isinstance(page, int) and page >= 1:
            lines.append(f"Claim page: {page}")
        evidence = str(item.get("evidence_span") or "").strip()
        if evidence:
            lines.append(f"> {evidence}")
        reason = str(item.get("reason") or "").strip()
        if reason:
            lines.append(reason)


def render_report(paper: dict[str, Any], conference_name: str = "") -> str:
    title = str(paper.get("title") or paper.get("arxiv_id") or "Untitled")
    arxiv_id = str(paper.get("arxiv_id") or "")
    status = str(paper.get("status") or "queued")
    issues = list(paper.get("issues") or [])
    claims = list(paper.get("claims") or [])
    summary = paper.get("summary") if isinstance(paper.get("summary"), dict) else summarize_claims(claims)
    lines = [f"# {title}", "", arxiv_id]
    author = str(paper.get("author_name") or "").strip()
    if author:
        lines.append(author)
    if conference_name:
        lines.append(conference_name)
    lines.extend(["", "## Verdict", ""])
    if status == "passed":
        lines.append(
            "Passed. The desk found no unresolved citation, missing number, unsupported claim, or failed rerun."
        )
    elif status == "contradicted":
        count = finding_count(claims, issues) or int(paper.get("issue_count") or 0)
        lines.append(f"Failed. The desk found {count} problem{'s' if count != 1 else ''}.")
    elif status == "error":
        lines.append("Not read. The desk could not open this paper.")
    else:
        lines.append("Not judged yet. Run the list, then open this report again.")

    if claims:
        summary_line = _summary_line(summary)
        if summary_line:
            lines.extend(["", summary_line])
            lines.append(_legend_line(summary))
        category_lines = _category_lines(summary)
        if category_lines:
            lines.append("")
            lines.extend(category_lines)
        findings = [claim for claim in claims if is_finding(claim)]
        for claim in findings:
            _append_finding_section(lines, claim)
    else:
        sentence = _finding_sentence(issues)
        if sentence:
            lines.extend(["", sentence])
        if status in _JUDGED:
            _append_issue_sections(lines, issues)

    lines.extend(["", "## Rerun", ""])
    kaggle = paper.get("kaggle") if isinstance(paper.get("kaggle"), dict) else None
    if not kaggle:
        lines.append("No rerun was recorded.")
    else:
        where = str(kaggle.get("where") or "not_run")
        rerun_status = str(kaggle.get("status") or "not_run")
        detail = str(kaggle.get("detail") or "").strip()
        lines.append(f"{where}: {rerun_status}.")
        if detail:
            lines.append(detail)
        kernel = str(kaggle.get("kernel_url") or "").strip()
        if kernel:
            lines.append(kernel)
        log = str(kaggle.get("log") or "").strip()
        if log:
            lines.extend(["", "```", log, "```"])

    lines.extend(["", "## How the desk read it", ""])
    events = list(paper.get("events") or [])
    finished = {str(event.get("specialist") or "") for event in events if event.get("state") == "finished"}
    failed_steps = {str(event.get("specialist") or "") for event in events if event.get("state") == "failed"}
    if not events and status not in _JUDGED:
        lines.append("The reading has not started.")
    else:
        for name in paper_audit.SPECIALISTS:
            if name in failed_steps:
                state = "failed"
            elif name in finished:
                state = "finished"
            elif status == "running" and paper.get("specialist") == name:
                state = "now"
            else:
                state = "not reached"
            lines.append(f"- {name.replace('_', ' ')}: {state}")

    return "\n".join(lines).rstrip() + "\n"


def paper_report(job_id: str) -> dict[str, str]:
    paper = paper_desk(job_id)
    return {
        "arxiv_id": str(paper.get("arxiv_id") or "paper"),
        "markdown": render_report(paper, _conference_name_for_job(job_id)),
    }


def conference_reports_zip(conference_id: str) -> bytes:
    desk = conference_desk(conference_id)
    judged = [paper for paper in desk["papers"] if paper.get("status") in _JUDGED]
    buffer = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if not judged:
            archive.writestr(
                "README.txt",
                "No paper on this list has been judged yet. Run the list, then download again.\n",
            )
        for paper in judged:
            full = paper_desk(str(paper["job_id"]))
            base = f"{full.get('arxiv_id') or 'paper'}.md"
            name = base if base not in used else f"{full.get('arxiv_id')}-{str(full.get('job_id'))[:8]}.md"
            used.add(name)
            archive.writestr(name, render_report(full, str(desk.get("name") or "")))
    return buffer.getvalue()


def run_cell(code: str) -> dict[str, Any]:
    """Run one notebook cell in a short-lived Python process."""
    source = code if isinstance(code, str) else ""
    if not source.strip():
        raise BatchError(400, "cell is empty")
    if len(source) > 8000:
        raise BatchError(400, "cell is too long")
    program = (
        "import io, contextlib, traceback\n"
        f"code = {source!r}\n"
        "try:\n"
        "    compiled = compile(code, '<cell>', 'exec')\n"
        "    buf = io.StringIO()\n"
        "    with contextlib.redirect_stdout(buf):\n"
        "        exec(compiled, {})\n"
        "    print(buf.getvalue(), end='')\n"
        "except Exception:\n"
        "    traceback.print_exc()\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        timeout=8,
        check=False,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    return {"ok": completed.returncode == 0, "output": output[-4000:]}


ASK_PROMPT = """You answer one conference chair about the papers on their list.
They can name a paper by its title or with @ and an arXiv id. Use only the paper text and issue list you are given.
Talk about fabricated citations, missing numbers, unsupported claims, and failed reruns.
AI-assisted writing is not a problem. Do not say a paper is fraudulent or that it was written by AI.
If a paper has not been read yet, say so. Quote a short span when you point at a problem.
Mention each finding once. Do not repeat the same citation, number, or claim.
Keep the reply to a few sentences the chair can use.
"""


def ask_conference(
    conference_id: str, question: str, mentions: list[str] | None = None
) -> dict[str, Any]:
    asked = question.strip()
    if not asked:
        raise BatchError(400, "question is empty")
    desk = conference_desk(conference_id)
    papers = desk["papers"]
    wish = parse_imagine(asked)
    if wish is not None:
        summary = desk_summary(desk["name"], papers)
        still = render_still(desk["name"], summary)
        url = generate_clip(still, motion_prompt(summary, wish))
        if url:
            answer = f"{summary}\n\nThe clip is ready."
        else:
            answer = f"{summary}\n\nThe clip was not generated."
        imagine = {
            "url": url,
            "prompt": wish,
            "summary": summary,
            "label": _IMAGINE_LABEL,
        }
        cited = [paper["arxiv_id"] for paper in papers]
        _store_exchange(
            conference_id, asked, answer, [], [], cited, imagine=imagine
        )
        return {
            "answer": answer,
            "papers": cited,
            "trace": [],
            "quotes": [],
            "action": None,
            "imagine": imagine,
        }
    named = set(mentions or [])
    named.update(_ARXIV_RE.findall(asked))
    lowered = asked.lower()
    for paper in papers:
        title = str(paper.get("title") or "").strip()
        if title and title.lower() in lowered:
            named.add(paper["arxiv_id"])
    if named:
        chosen = [paper for paper in papers if paper["arxiv_id"] in named]
    else:
        chosen = papers
    if named and not chosen:
        answer = "None of those ids are on this conference list."
        _store_exchange(conference_id, asked, answer, [], [], [])
        return {
            "answer": answer,
            "papers": [],
            "trace": [],
            "quotes": [],
        }
    answer, action = voice.finish(asked, chosen, _grok_answer, _local_answer, desk['name'])
    trace, quotes = _reading(chosen, answer)
    cited = [paper["arxiv_id"] for paper in chosen]
    _store_exchange(conference_id, asked, answer, trace, quotes, cited)
    return {
        "answer": answer,
        "papers": cited,
        "trace": trace,
        "quotes": quotes,
        "action": action,
    }


def clear_conference_messages(conference_id: str) -> dict[str, int]:
    with _db() as conn:
        _ensure_desk(conn)
        row = conn.execute(
            "SELECT 1 FROM conferences WHERE conference_id = ?",
            (conference_id,),
        ).fetchone()
        if row is None:
            raise BatchError(404, "conference not found")
        cursor = conn.execute(
            "DELETE FROM desk_messages WHERE conference_id = ?",
            (conference_id,),
        )
        conn.commit()
        return {"cleared": int(cursor.rowcount)}


def conference_messages(conference_id: str) -> dict[str, Any]:
    with _db() as conn:
        _ensure_desk(conn)
        row = conn.execute(
            "SELECT 1 FROM conferences WHERE conference_id = ?",
            (conference_id,),
        ).fetchone()
        if row is None:
            raise BatchError(404, "conference not found")
        rows = conn.execute(
            """
            SELECT role, body, trace_json, quotes_json, papers_json, imagine_json
            FROM desk_messages
            WHERE conference_id = ?
            ORDER BY position ASC
            """,
            (conference_id,),
        ).fetchall()
    messages: list[dict[str, Any]] = []
    for item in rows:
        message: dict[str, Any] = {"role": item["role"], "text": item["body"]}
        if item["role"] == "desk":
            message["trace"] = json.loads(item["trace_json"] or "[]")
            message["quotes"] = json.loads(item["quotes_json"] or "[]")
            message["papers"] = json.loads(item["papers_json"] or "[]")
            raw_imagine = item["imagine_json"]
            if raw_imagine:
                parsed = json.loads(raw_imagine)
                if isinstance(parsed, dict):
                    message["imagine"] = parsed
        messages.append(message)
    return {"messages": messages}


def _store_exchange(
    conference_id: str,
    question: str,
    answer: str,
    trace: list[dict[str, Any]],
    quotes: list[dict[str, Any]],
    papers: list[str],
    imagine: dict[str, Any] | None = None,
) -> None:
    with _db() as conn:
        _ensure_desk(conn)
        position = conn.execute(
            "SELECT COALESCE(MAX(position), 0) FROM desk_messages WHERE conference_id = ?",
            (conference_id,),
        ).fetchone()[0]
        created = _now()
        conn.execute(
            """
            INSERT INTO desk_messages (
                message_id, conference_id, position, role, body,
                trace_json, quotes_json, papers_json, imagine_json, created_at
            ) VALUES (?, ?, ?, 'you', ?, '[]', '[]', '[]', NULL, ?)
            """,
            (str(uuid4()), conference_id, int(position) + 1, question, created),
        )
        conn.execute(
            """
            INSERT INTO desk_messages (
                message_id, conference_id, position, role, body,
                trace_json, quotes_json, papers_json, imagine_json, created_at
            ) VALUES (?, ?, ?, 'desk', ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                conference_id,
                int(position) + 2,
                answer,
                json.dumps(trace),
                json.dumps(quotes),
                json.dumps(papers),
                json.dumps(imagine) if imagine is not None else None,
                created,
            ),
        )
        conn.commit()


def paper_file(job_id: str) -> tuple[bytes, str]:
    with _db() as conn:
        _ensure_desk(conn)
        job = conn.execute(
            "SELECT arxiv_id FROM paper_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
    if job is None:
        raise BatchError(404, "paper not found")
    try:
        path, _author = resolve_paper(job["arxiv_id"])
    except PaperLoadError as exc:
        raise BatchError(404, str(exc)) from exc
    payload = path.read_bytes()
    if not payload.startswith(b"%PDF"):
        raise BatchError(404, "pdf is missing")
    return payload, str(job["arxiv_id"])


def _reading(
    papers: list[dict[str, Any]], answer: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    quotes: list[dict[str, Any]] = []
    for paper in papers:
        body = " ".join(str(paper.get("paper_text") or "").split())
        for issue in paper.get("issues") or []:
            text = " ".join(str(issue.get("evidence_span") or issue.get("claim_text") or "").split())
            if len(text) < 4:
                continue
            page = issue.get("page")
            quotes.append(
                {
                    "quote_id": f"q{len(quotes) + 1}",
                    "job_id": paper["job_id"],
                    "arxiv_id": paper["arxiv_id"],
                    "title": paper.get("title") or paper["arxiv_id"],
                    "page": page if isinstance(page, int) else None,
                    "text": text,
                    "issue_type": str(issue.get("issue_type") or ""),
                    "reason": str(issue.get("reason") or ""),
                }
            )
        for sentence in _answer_sentences(answer):
            compact = " ".join(sentence.split())
            if len(compact) < 24 or compact not in body:
                continue
            if any(item["text"] == compact and item["arxiv_id"] == paper["arxiv_id"] for item in quotes):
                continue
            quotes.append(
                {
                    "quote_id": f"q{len(quotes) + 1}",
                    "job_id": paper["job_id"],
                    "arxiv_id": paper["arxiv_id"],
                    "title": paper.get("title") or paper["arxiv_id"],
                    "page": _page_in_text(paper, compact),
                    "text": compact,
                    "issue_type": "",
                    "reason": "",
                }
            )
    trace: list[dict[str, Any]] = []
    for paper in papers:
        trace.append(
            {
                "id": f"choose-{paper['arxiv_id']}",
                "kind": "choose",
                "label": paper.get("title") or paper["arxiv_id"],
                "detail": paper["arxiv_id"],
                "quote_id": None,
            }
        )
        trace.append(
            {
                "id": f"verdict-{paper['arxiv_id']}",
                "kind": "verdict",
                "label": _verdict_label(paper),
                "detail": paper["arxiv_id"],
                "quote_id": None,
            }
        )
        for quote in quotes:
            if quote["arxiv_id"] != paper["arxiv_id"] or not quote["issue_type"]:
                continue
            trace.append(
                {
                    "id": quote["quote_id"],
                    "kind": "quote",
                    "label": quote["issue_type"],
                    "detail": quote["reason"],
                    "quote_id": quote["quote_id"],
                }
            )
    return trace, quotes


def _verdict_label(paper: dict[str, Any]) -> str:
    status = str(paper.get("status") or "")
    issues = paper.get("issues") or []
    text = str(paper.get("paper_text") or "").strip()
    if status == "queued" or (status not in {"error", "passed", "contradicted"} and not text and not issues):
        return "Still queued"
    if status == "passed":
        return "Passed"
    if status == "error":
        return "Not read"
    if status == "contradicted":
        count = len(issues)
        word = "problem" if count == 1 else "problems"
        return f"Failed. {count} {word}"
    if status == "running":
        return "Still reading"
    return "Not judged yet"


def _answer_sentences(answer: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", answer.strip()) if part.strip()]


def _page_in_text(paper: dict[str, Any], sentence: str) -> int | None:
    for issue in paper.get("issues") or []:
        span = " ".join(str(issue.get("evidence_span") or "").split())
        claim = " ".join(str(issue.get("claim_text") or "").split())
        if sentence in claim or (span and span in sentence):
            page = issue.get("page")
            if isinstance(page, int):
                return page
    return None


def _local_answer(papers: list[dict[str, Any]]) -> str:
    if not papers:
        return "This conference list is empty. Add papers, then ask again."
    lines: list[str] = []
    for paper in papers:
        issues = paper.get("issues") or []
        label = paper.get("title") or paper["arxiv_id"]
        if not paper.get("paper_text") and not issues:
            lines.append(f"{label} ({paper['arxiv_id']}) is still queued.")
            continue
        if not issues:
            lines.append(f"{label} ({paper['arxiv_id']}) has nothing to report.")
            continue
        for issue in issues:
            lines.append(
                f"{label} ({paper['arxiv_id']}) {issue['issue_type']}: {issue['reason']}"
            )
    return "\n".join(lines)


def _grok_answer(conference: str, question: str, papers: list[dict[str, Any]]) -> str | None:
    key = os.environ.get("XAI_API_KEY", "").strip()
    if not key:
        return None
    blocks = []
    for paper in papers:
        issues = paper.get("issues") or []
        issue_lines = "\n".join(
            f"- {item['issue_type']}: {item['reason']} | {item['evidence_span']}"
            for item in issues
        ) or "- none"
        text = (paper.get("paper_text") or "").strip() or (paper.get("abstract") or "").strip()
        text = text[:4000]
        blocks.append(
            f"{paper.get('title') or 'Untitled'} @{paper['arxiv_id']} status {paper['status']}\n"
            f"Issues:\n{issue_lines}\nClaims:\n{voice.claim_lines(paper)}\n{text}"
        )
    user = f"Conference: {conference}\n\n" + "\n\n".join(blocks) + f"\n\nQuestion: {question}"
    try:
        import httpx

        response = httpx.post(
            "https://api.x.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": "grok-4.6",
                "messages": [
                    {"role": "system", "content": ASK_PROMPT},
                    {"role": "user", "content": user},
                ],
            },
            timeout=30,
        )
    except Exception:
        return None
    if response.status_code != 200:
        return None
    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    return content if isinstance(content, str) and content.strip() else None
