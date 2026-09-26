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
from typing import Any
from uuid import uuid4

import paper_audit
import repro
import shelf
from models import DeskClaim, is_finding
from batches import (
    LOCAL_PAPERS,
    BatchError,
    PaperLoadError,
    _db,
    _events_for_jobs,
    _issues_for_jobs,
    _now,
    arxiv_listings,
    resolve_paper,
)

_ARXIV_RE = re.compile(r"(\d{4}\.\d{4,5}|0000\.0000\d)")
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
        CREATE TABLE IF NOT EXISTS desk_messages (
            message_id TEXT PRIMARY KEY,
            conference_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            role TEXT NOT NULL,
            body TEXT NOT NULL,
            trace_json TEXT NOT NULL,
            quotes_json TEXT NOT NULL,
            papers_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
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
                conn.execute(
                    "UPDATE conferences SET owner = ? WHERE owner IS NULL",
                    (user_id,),
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


def list_conferences(owner: str | None = None) -> list[dict[str, Any]]:
    with _db() as conn:
        _ensure_desk(conn)
        if owner:
            rows = conn.execute(
                "SELECT * FROM conferences WHERE owner = ? ORDER BY name ASC",
                (owner,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM conferences ORDER BY name ASC").fetchall()
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
            SELECT paper_jobs.arxiv_id, paper_jobs.listing_title
            FROM paper_jobs
            JOIN batches ON batches.batch_id = paper_jobs.batch_id
            WHERE batches.conference_id = ?
            """,
            (conference_id,),
        ).fetchall()
        existing = {row["arxiv_id"] for row in rows}
        blank = {row["arxiv_id"] for row in rows if not (row["listing_title"] or "").strip()}
    fresh = [arxiv_id for arxiv_id in ids if arxiv_id not in existing]
    stale = [arxiv_id for arxiv_id in ids if arxiv_id in blank]
    if not fresh and not stale:
        return {
            "conference_id": conference_id,
            "added": 0,
            "already": len(ids),
            "arxiv_ids": [],
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


def _drain(conference_id: str, cap: int | None) -> None:
    try:
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
        for job_id in job_ids:
            _audit_job(job_id)
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
        claim = DeskClaim.model_validate({**raw, "job_id": job_id})
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
        "categories": {
            "citations": {"resolved": 0, "total": 0},
            "internal": {"supported": 0, "total": 0},
            "numerical": {"consistent": 0, "total": 0},
            "computational": {"reproduced": 0, "total": 0},
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
        if kind == "citation":
            categories["citations"]["total"] += 1
            if verdict == "supported":
                categories["citations"]["resolved"] += 1
        elif kind == "semantic":
            categories["internal"]["total"] += 1
            if verdict == "supported":
                categories["internal"]["supported"] += 1
        elif kind in ("numerical", "numerical_comparison"):
            categories["numerical"]["total"] += 1
            if verdict == "supported":
                categories["numerical"]["consistent"] += 1
        elif kind == "dataset":
            categories["computational"]["total"] += 1
            if verdict == "reproduced":
                categories["computational"]["reproduced"] += 1
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
    "0000.00001": "Hallucinated Metric Paper",
    "0000.00002": "Measured Metric Paper",
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


def render_report(paper: dict[str, Any], conference_name: str = "") -> str:
    title = str(paper.get("title") or paper.get("arxiv_id") or "Untitled")
    arxiv_id = str(paper.get("arxiv_id") or "")
    status = str(paper.get("status") or "queued")
    issues = list(paper.get("issues") or [])
    lines = [f"# {title}", "", arxiv_id]
    author = str(paper.get("author_name") or "").strip()
    if author:
        lines.append(author)
    if conference_name:
        lines.append(conference_name)
    lines.extend(["", "## Verdict", ""])
    if status == "passed":
        lines.append(
            "Passed. The desk found no fabricated citation, missing number, unsupported claim, or failed rerun."
        )
    elif status == "contradicted":
        count = len(issues) or int(paper.get("issue_count") or 0)
        lines.append(f"Failed. The desk found {count} problem{'s' if count != 1 else ''}.")
    elif status == "error":
        lines.append("Not read. The desk could not open this paper.")
    else:
        lines.append("Not judged yet. Run the list, then open this report again.")

    sentence = _finding_sentence(issues)
    if sentence:
        lines.extend(["", sentence])

    failed = [item for item in issues if item.get("issue_type") != "ai_likeness"]
    lines.extend(["", "## What failed", ""])
    if status not in _JUDGED:
        lines.append("This paper has not been judged yet.")
    elif not failed:
        lines.append("Nothing failed.")
    else:
        for item in failed:
            kind = _CHECK_LABELS.get(str(item.get("issue_type") or ""), str(item.get("issue_type") or "Check"))
            lines.extend([f"### {kind}", ""])
            claim = str(item.get("claim_text") or "").strip()
            if claim:
                lines.extend([claim, ""])
            page = item.get("page")
            if isinstance(page, int) and page >= 1:
                lines.append(f"Page {page}.")
            evidence = str(item.get("evidence_span") or "").strip()
            if evidence:
                lines.append(f"> {evidence}")
            reason = str(item.get("reason") or "").strip()
            if reason:
                lines.append(reason)
            lines.append("")

    lines.extend(["## What passed", ""])
    if status not in _JUDGED:
        lines.append("Nothing has been checked yet.")
    elif status == "error":
        lines.append("The reading did not finish, so no check passed.")
    else:
        failed_types = {str(item.get("issue_type") or "") for item in failed}
        passed_lines = []
        for key, label in _CHECK_LABELS.items():
            if key == "test":
                continue
            if key not in failed_types:
                passed_lines.append(f"- {label} passed.")
        kaggle = paper.get("kaggle") if isinstance(paper.get("kaggle"), dict) else {}
        rerun = str((kaggle or {}).get("status") or "not_run")
        if rerun == "match":
            passed_lines.append("- The rerun matched the count written in the paper.")
        if not passed_lines:
            lines.append("No check passed.")
        else:
            lines.extend(passed_lines)

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
        chosen = papers[:6]
    if named and not chosen:
        answer = "None of those ids are on this conference list."
        _store_exchange(conference_id, asked, answer, [], [], [])
        return {
            "answer": answer,
            "papers": [],
            "trace": [],
            "quotes": [],
        }
    answer = _grok_answer(desk["name"], asked, chosen) or _local_answer(chosen)
    trace, quotes = _reading(chosen, answer)
    cited = [paper["arxiv_id"] for paper in chosen]
    _store_exchange(conference_id, asked, answer, trace, quotes, cited)
    return {
        "answer": answer,
        "papers": cited,
        "trace": trace,
        "quotes": quotes,
    }


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
            SELECT role, body, trace_json, quotes_json, papers_json
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
        messages.append(message)
    return {"messages": messages}


def _store_exchange(
    conference_id: str,
    question: str,
    answer: str,
    trace: list[dict[str, Any]],
    quotes: list[dict[str, Any]],
    papers: list[str],
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
                trace_json, quotes_json, papers_json, created_at
            ) VALUES (?, ?, ?, 'you', ?, '[]', '[]', '[]', ?)
            """,
            (str(uuid4()), conference_id, int(position) + 1, question, created),
        )
        conn.execute(
            """
            INSERT INTO desk_messages (
                message_id, conference_id, position, role, body,
                trace_json, quotes_json, papers_json, created_at
            ) VALUES (?, ?, ?, 'desk', ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                conference_id,
                int(position) + 2,
                answer,
                json.dumps(trace),
                json.dumps(quotes),
                json.dumps(papers),
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
            lines.append(f"{label} ({paper['arxiv_id']}) has no fabricated-claim flags.")
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
            f"{paper.get('title') or 'Untitled'} @{paper['arxiv_id']} status {paper['status']}\n{issue_lines}\n{text}"
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
