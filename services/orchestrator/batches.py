from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import jev
import paper_audit
import store

FIXTURES = Path(__file__).resolve().parent / "fixtures"
LOCAL_PAPERS = {
    "0000.00001": (FIXTURES / "hallucinated.pdf", "Ada Example"),
    "0000.00002": (FIXTURES / "human.pdf", "Lin Example"),
}
_JEV_LABELS = frozenset({"supported", "contradicted", "not_mentioned"})
_MAX_ARXIV_IDS = 8


class BatchError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class PaperLoadError(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_tables(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conferences (
            conference_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            contact_email TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS batches (
            batch_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            name TEXT,
            arxiv_ids TEXT NOT NULL,
            conference_id TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS paper_jobs (
            job_id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL,
            arxiv_id TEXT NOT NULL,
            run_id TEXT,
            status TEXT NOT NULL,
            specialist TEXT,
            fitness REAL,
            issue_count INTEGER NOT NULL,
            author_name TEXT,
            author_email TEXT,
            contacted_at TEXT,
            position INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS job_events (
            event_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            specialist TEXT NOT NULL,
            state TEXT NOT NULL,
            detail TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS paper_issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            issue_type TEXT NOT NULL,
            claim_text TEXT NOT NULL,
            evidence_span TEXT NOT NULL,
            jev_label TEXT NOT NULL,
            reason TEXT NOT NULL
        )
        """
    )
    conn.commit()


@contextmanager
def _db() -> Iterator[Any]:
    conn = store.connect(store.default_db_path())
    try:
        _ensure_tables(conn)
        yield conn
    finally:
        conn.close()


def resolve_paper(arxiv_id: str) -> tuple[Path, str]:
    mapped = LOCAL_PAPERS.get(arxiv_id)
    if mapped is None:
        raise PaperLoadError(f"unknown arxiv id: {arxiv_id}")
    path, author_name = mapped
    if not path.is_file():
        raise PaperLoadError(f"missing fixture for {arxiv_id}")
    return path, author_name


def _job_dict(row: Any) -> dict[str, Any]:
    return {
        "job_id": row["job_id"],
        "batch_id": row["batch_id"],
        "arxiv_id": row["arxiv_id"],
        "run_id": row["run_id"],
        "status": row["status"],
        "specialist": row["specialist"],
        "fitness": row["fitness"],
        "issue_count": row["issue_count"],
        "author_name": row["author_name"],
        "author_email": row["author_email"],
        "contacted_at": row["contacted_at"],
    }


def _issue_dict(row: Any) -> dict[str, Any]:
    return {
        "issue_type": row["issue_type"],
        "claim_text": row["claim_text"],
        "evidence_span": row["evidence_span"],
        "jev_label": row["jev_label"],
        "reason": row["reason"],
    }


def _event_dict(row: Any) -> dict[str, Any]:
    return {
        "event_id": row["event_id"],
        "job_id": row["job_id"],
        "specialist": row["specialist"],
        "state": row["state"],
        "detail": row["detail"],
        "created_at": row["created_at"],
    }


def _jobs_for_batch(conn: Any, batch_id: str) -> list[Any]:
    return conn.execute(
        """
        SELECT * FROM paper_jobs
        WHERE batch_id = ?
        ORDER BY position ASC
        """,
        (batch_id,),
    ).fetchall()


def _issues_for_jobs(conn: Any, job_ids: list[str]) -> list[dict[str, Any]]:
    if not job_ids:
        return []
    placeholders = ",".join("?" * len(job_ids))
    rows = conn.execute(
        f"""
        SELECT paper_issues.*
        FROM paper_issues
        JOIN paper_jobs ON paper_jobs.job_id = paper_issues.job_id
        WHERE paper_issues.job_id IN ({placeholders})
        ORDER BY paper_jobs.position ASC, paper_issues.id ASC
        """,
        job_ids,
    ).fetchall()
    return [_issue_dict(row) for row in rows]


def _events_for_jobs(conn: Any, job_ids: list[str]) -> list[dict[str, Any]]:
    if not job_ids:
        return []
    placeholders = ",".join("?" * len(job_ids))
    rows = conn.execute(
        f"""
        SELECT job_events.*
        FROM job_events
        JOIN paper_jobs ON paper_jobs.job_id = job_events.job_id
        WHERE job_events.job_id IN ({placeholders})
        ORDER BY paper_jobs.position ASC, job_events.created_at ASC
        """,
        job_ids,
    ).fetchall()
    return [_event_dict(row) for row in rows]


def _read_batch(conn: Any, batch_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM batches WHERE batch_id = ?",
        (batch_id,),
    ).fetchone()
    if row is None:
        raise BatchError(404, "batch not found")
    jobs = [_job_dict(job) for job in _jobs_for_batch(conn, batch_id)]
    job_ids = [job["job_id"] for job in jobs]
    return {
        "batch_id": row["batch_id"],
        "kind": row["kind"],
        "name": row["name"],
        "arxiv_ids": json.loads(row["arxiv_ids"]),
        "created_at": row["created_at"],
        "jobs": jobs,
        "events": _events_for_jobs(conn, job_ids),
        "claims": _issues_for_jobs(conn, job_ids),
    }


def _insert_job(
    conn: Any,
    *,
    job_id: str,
    batch_id: str,
    arxiv_id: str,
    run_id: str,
    status: str,
    specialist: str | None,
    fitness: float,
    issue_count: int,
    author_name: str | None,
    position: int,
) -> None:
    conn.execute(
        """
        INSERT INTO paper_jobs (
            job_id, batch_id, arxiv_id, run_id, status, specialist,
            fitness, issue_count, author_name, author_email, contacted_at, position
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?)
        """,
        (
            job_id,
            batch_id,
            arxiv_id,
            run_id,
            status,
            specialist,
            fitness,
            issue_count,
            author_name,
            position,
        ),
    )


def _persist_events(conn: Any, job_id: str, events: list[dict[str, Any]]) -> None:
    now = _now()
    for event in events:
        conn.execute(
            """
            INSERT INTO job_events (
                event_id, job_id, specialist, state, detail, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                job_id,
                str(event.get("specialist") or ""),
                str(event.get("state") or ""),
                str(event.get("detail") or ""),
                now,
            ),
        )


def _persist_issues(conn: Any, job_id: str, issues: list[dict[str, Any]]) -> None:
    for issue in issues:
        conn.execute(
            """
            INSERT INTO paper_issues (
                job_id, issue_type, claim_text, evidence_span, jev_label, reason
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                str(issue.get("issue_type") or ""),
                str(issue.get("claim_text") or ""),
                str(issue.get("evidence_span") or ""),
                str(issue.get("jev_label") or ""),
                str(issue.get("reason") or ""),
            ),
        )


def _apply_jev(issues: list[dict[str, Any]]) -> None:
    for issue in issues:
        verdict = jev.judge_claim(
            str(issue.get("claim_text") or ""),
            str(issue.get("evidence_span") or ""),
        )
        if not isinstance(verdict, dict) or verdict.get("not_run"):
            continue
        label = verdict.get("label")
        if label in _JEV_LABELS:
            issue["jev_label"] = label


def _process_job(conn: Any, batch_id: str, arxiv_id: str, position: int) -> None:
    job_id = str(uuid4())
    run_id = str(uuid4())
    try:
        path, author_name = resolve_paper(arxiv_id)
    except PaperLoadError:
        _insert_job(
            conn,
            job_id=job_id,
            batch_id=batch_id,
            arxiv_id=arxiv_id,
            run_id=run_id,
            status="error",
            specialist=None,
            fitness=0.0,
            issue_count=0,
            author_name=None,
            position=position,
        )
        return

    result = paper_audit.audit_paper(path, job_id)
    issues = list(result.get("issues") or [])
    _apply_jev(issues)
    _persist_events(conn, job_id, list(result.get("events") or []))
    _persist_issues(conn, job_id, issues)
    contradicted = bool(issues)
    _insert_job(
        conn,
        job_id=job_id,
        batch_id=batch_id,
        arxiv_id=arxiv_id,
        run_id=run_id,
        status="contradicted" if contradicted else "passed",
        specialist="jev",
        fitness=0.0 if contradicted else 1.0,
        issue_count=len(issues),
        author_name=author_name,
        position=position,
    )


def create_batch(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("product") != "arxaudit":
        raise BatchError(400, "product must be arxaudit")
    kind = payload.get("kind")
    if kind not in {"links", "batch"}:
        raise BatchError(400, "kind must be links or batch")
    name = payload.get("name")
    if kind == "batch" and (name is None or not str(name).strip()):
        raise BatchError(400, "name is required for kind batch")
    if kind == "links":
        name = None
    conference_id = payload.get("conference_id")
    if kind == "links" and conference_id is not None:
        raise BatchError(400, "links cannot set conference_id")
    arxiv_ids = list(payload.get("arxiv_ids") or [])
    if len(arxiv_ids) > _MAX_ARXIV_IDS:
        raise BatchError(400, "arxiv_ids max is 8")

    batch_id = str(uuid4())
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO batches (
                batch_id, kind, name, arxiv_ids, conference_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id,
                kind,
                name,
                json.dumps(arxiv_ids),
                conference_id,
                _now(),
            ),
        )
        for position, arxiv_id in enumerate(arxiv_ids):
            _process_job(conn, batch_id, str(arxiv_id), position)
        conn.commit()
        return _read_batch(conn, batch_id)


def get_batch(batch_id: str) -> dict[str, Any]:
    with _db() as conn:
        return _read_batch(conn, batch_id)


def create_conference(payload: dict[str, Any]) -> dict[str, Any]:
    conference_id = str(uuid4())
    name = str(payload.get("name") or "")
    contact_email = str(payload.get("contact_email") or "")
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO conferences (conference_id, name, contact_email)
            VALUES (?, ?, ?)
            """,
            (conference_id, name, contact_email),
        )
        conn.commit()
    return {
        "conference_id": conference_id,
        "name": name,
        "contact_email": contact_email,
    }


def get_conference(conference_id: str) -> dict[str, Any]:
    with _db() as conn:
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
            ORDER BY batches.created_at ASC, paper_jobs.position ASC
            """,
            (conference_id,),
        ).fetchall()
        papers = []
        for job in jobs:
            papers.append(
                {
                    "arxiv_id": job["arxiv_id"],
                    "author_name": job["author_name"],
                    "author_email": job["author_email"],
                    "status": job["status"],
                    "contacted_at": job["contacted_at"],
                    "issues": _issues_for_jobs(conn, [job["job_id"]]),
                }
            )
        return {
            "conference_id": row["conference_id"],
            "name": row["name"],
            "contact_email": row["contact_email"],
            "papers": papers,
        }


def patch_paper(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM paper_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            raise BatchError(404, "paper not found")
        author_email = payload.get("author_email", row["author_email"])
        contacted_at = payload.get("contacted_at", row["contacted_at"])
        conn.execute(
            """
            UPDATE paper_jobs
            SET author_email = ?, contacted_at = ?
            WHERE job_id = ?
            """,
            (author_email, contacted_at, job_id),
        )
        conn.commit()
        updated = conn.execute(
            "SELECT * FROM paper_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        return _job_dict(updated)
