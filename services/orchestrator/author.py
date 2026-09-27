"""One shelf and one thread per author. The chair list is a different conference."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from batches import BatchError, _db
from desk import (
    DEMO_CONFERENCE_ID,
    _ensure_desk,
    add_submissions,
    add_upload,
    conference_desk,
    paper_desk,
    parse_arxiv_id,
    start_run,
)

SHELF_NAME = "Author shelf"
SHELF_EMAIL = "author@arxaudit.local"


def _tables(conn: Any) -> None:
    _ensure_desk(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS author_shelves (
            owner TEXT PRIMARY KEY,
            conference_id TEXT NOT NULL
        )
        """
    )


def _shelf_id(owner: str, create: bool) -> str | None:
    cleaned = owner.strip()
    if not cleaned:
        raise BatchError(400, "owner is required")
    with _db() as conn:
        _tables(conn)
        row = conn.execute(
            "SELECT conference_id FROM author_shelves WHERE owner = ?",
            (cleaned,),
        ).fetchone()
        if row is not None:
            return str(row["conference_id"])
        if not create:
            return None
        conference_id = str(uuid4())
        conn.execute(
            """
            INSERT INTO conferences (conference_id, name, contact_email, owner)
            VALUES (?, ?, ?, ?)
            """,
            (conference_id, SHELF_NAME, SHELF_EMAIL, cleaned),
        )
        conn.execute(
            "INSERT INTO author_shelves (owner, conference_id) VALUES (?, ?)",
            (cleaned, conference_id),
        )
        conn.commit()
        return conference_id


def _job(conference_id: str, arxiv_id: str) -> dict[str, Any] | None:
    with _db() as conn:
        _tables(conn)
        row = conn.execute(
            """
            SELECT paper_jobs.job_id, paper_jobs.arxiv_id,
                   paper_jobs.listing_title, paper_jobs.status
            FROM paper_jobs
            JOIN batches ON batches.batch_id = paper_jobs.batch_id
            WHERE batches.conference_id = ? AND paper_jobs.arxiv_id = ?
            ORDER BY paper_jobs.position DESC
            LIMIT 1
            """,
            (conference_id, arxiv_id),
        ).fetchone()
    if row is None:
        return None
    return {
        "job_id": row["job_id"],
        "arxiv_id": row["arxiv_id"],
        "title": (row["listing_title"] or "").strip() or row["arxiv_id"],
        "status": row["status"],
    }


def _on_shelf(job_id: str) -> bool:
    with _db() as conn:
        _tables(conn)
        row = conn.execute(
            """
            SELECT 1
            FROM paper_jobs
            JOIN batches ON batches.batch_id = paper_jobs.batch_id
            JOIN author_shelves ON author_shelves.conference_id = batches.conference_id
            WHERE paper_jobs.job_id = ?
            """,
            (job_id,),
        ).fetchone()
    return row is not None


def add_author_paper(owner: str, arxiv_id: str | None = None, pdf: bytes | None = None) -> dict[str, str]:
    conference_id = _shelf_id(owner, create=True)
    if conference_id is None:
        raise BatchError(400, "owner is required")
    if pdf:
        added = add_upload(conference_id, pdf, owner=owner.strip())
        ident = str(added["arxiv_id"])
    elif arxiv_id and parse_arxiv_id(arxiv_id):
        ident = parse_arxiv_id(arxiv_id) or ""
        add_submissions(conference_id, [ident], owner=owner.strip())
    else:
        raise BatchError(400, "paste an arXiv id or upload a PDF")
    row = _job(conference_id, ident)
    if row is None:
        raise BatchError(404, "paper not found")
    start_run(conference_id, None)
    fresh = _job(conference_id, ident) or row
    return {
        "job_id": str(fresh["job_id"]),
        "arxiv_id": str(fresh["arxiv_id"]),
        "title": str(fresh["title"]),
        "status": str(fresh["status"]),
    }


def list_author_papers(owner: str) -> dict[str, list[dict[str, str]]]:
    conference_id = _shelf_id(owner, create=False)
    if conference_id is None:
        return {"papers": []}
    desk = conference_desk(conference_id)
    papers = [
        {
            "job_id": str(paper["job_id"]),
            "arxiv_id": str(paper["arxiv_id"]),
            "title": str(paper["title"]),
            "status": str(paper["status"]),
        }
        for paper in desk["papers"]
    ]
    return {"papers": papers}


def get_author_paper(job_id: str) -> dict[str, Any]:
    if not _on_shelf(job_id):
        raise BatchError(404, "paper not found")
    paper = paper_desk(job_id)
    if paper.get("conference_id") == DEMO_CONFERENCE_ID:
        raise BatchError(404, "paper not found")
    return paper
