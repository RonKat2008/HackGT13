"""One shelf and one thread per author. The chair list is a different conference."""

from __future__ import annotations

import json
import os
from typing import Any
from uuid import uuid4

import voice
from batches import BatchError, _db, _now
from desk import (
    DEMO_CONFERENCE_ID,
    _ensure_desk,
    _reading,
    add_submissions,
    add_upload,
    conference_desk,
    paper_desk,
    parse_arxiv_id,
    start_run,
)

SHELF_NAME = "Author shelf"
SHELF_EMAIL = "author@arxaudit.local"

AUTHOR_PROMPT = """You answer one author about one paper of theirs.
Use only that paper's stored text, the issue list, and the stored claims you are given.
You can list findings, point at a page, and explain a stored formula.
You cannot change a verdict. If asked, say the desk does not change a verdict from chat.
Talk about unresolved citations, missing numbers, unsupported claims, and failed reruns.
A sentence that needs a person was left unsure. Leave it that way.
Stay with the stored citation, number, formula, and passage.
Do not say fake, fraudulent, fabricated, or AI-written.
If the paper status is queued or running, say the read has not finished.
Quote a short span when you point at a problem.
Mention each finding once. Do not repeat the same citation, number, or claim.
Keep the reply to a few sentences the author can use.
"""

_REFUSE_SENTENCE = (
    "The desk does not change a verdict from chat. The stored read stays as it is."
)


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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS author_messages (
            message_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            role TEXT NOT NULL,
            body TEXT NOT NULL,
            quotes_json TEXT NOT NULL DEFAULT '[]',
            trace_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
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


def _load_history(job_id: str, limit: int = 12) -> list[dict[str, str]]:
    with _db() as conn:
        _tables(conn)
        rows = conn.execute(
            """
            SELECT role, body
            FROM author_messages
            WHERE job_id = ?
            ORDER BY position DESC
            LIMIT ?
            """,
            (job_id, limit),
        ).fetchall()
    rows = list(reversed(rows))
    return [{"role": str(row["role"]), "text": str(row["body"])} for row in rows]


def _store_exchange(
    job_id: str,
    question: str,
    answer: str,
    quotes: list[dict[str, Any]],
    trace: list[dict[str, Any]],
) -> None:
    with _db() as conn:
        _tables(conn)
        position = conn.execute(
            "SELECT COALESCE(MAX(position), 0) FROM author_messages WHERE job_id = ?",
            (job_id,),
        ).fetchone()[0]
        created = _now()
        conn.execute(
            """
            INSERT INTO author_messages (
                message_id, job_id, position, role, body,
                quotes_json, trace_json, created_at
            ) VALUES (?, ?, ?, 'you', ?, '[]', '[]', ?)
            """,
            (str(uuid4()), job_id, int(position) + 1, question, created),
        )
        conn.execute(
            """
            INSERT INTO author_messages (
                message_id, job_id, position, role, body,
                quotes_json, trace_json, created_at
            ) VALUES (?, ?, ?, 'desk', ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                job_id,
                int(position) + 2,
                answer,
                json.dumps(quotes),
                json.dumps(trace),
                created,
            ),
        )
        conn.commit()


def list_author_messages(job_id: str) -> dict[str, list[dict[str, Any]]]:
    if not _on_shelf(job_id):
        raise BatchError(404, "paper not found")
    with _db() as conn:
        _tables(conn)
        rows = conn.execute(
            """
            SELECT role, body, quotes_json, trace_json
            FROM author_messages
            WHERE job_id = ?
            ORDER BY position ASC
            """,
            (job_id,),
        ).fetchall()
    messages: list[dict[str, Any]] = []
    for item in rows:
        message: dict[str, Any] = {"role": item["role"], "text": item["body"]}
        if item["role"] == "desk":
            quotes = json.loads(item["quotes_json"] or "[]")
            trace = json.loads(item["trace_json"] or "[]")
            if quotes:
                message["quotes"] = quotes
            if trace:
                message["trace"] = trace
        messages.append(message)
    return {"messages": messages}


def _paper_block(paper: dict[str, Any]) -> str:
    issues = paper.get("issues") or []
    issue_lines = "\n".join(
        f"- {item['issue_type']}: {item['reason']} | {item['evidence_span']}"
        for item in issues
    ) or "- none"
    text = (paper.get("paper_text") or "").strip() or (paper.get("abstract") or "").strip()
    text = text[:4000]
    return (
        f"{paper.get('title') or 'Untitled'} @{paper['arxiv_id']} status {paper['status']}\n"
        f"Issues:\n{issue_lines}\nClaims:\n{voice.claim_lines(paper)}\n{text}"
    )


def _grok_messages(
    paper: dict[str, Any], question: str, history: list[dict[str, str]]
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [
        {"role": "system", "content": AUTHOR_PROMPT + "\n\n" + _paper_block(paper)},
    ]
    for turn in history[-12:]:
        role = "user" if turn["role"] == "you" else "assistant"
        messages.append({"role": role, "content": turn["text"]})
    messages.append({"role": "user", "content": question})
    return messages


def _post_grok(messages: list[dict[str, str]]) -> str | None:
    key = os.environ.get("XAI_API_KEY", "").strip()
    if not key:
        return None
    try:
        import httpx

        response = httpx.post(
            "https://api.x.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "grok-4.6", "messages": messages},
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


def _author_grok(
    paper: dict[str, Any], question: str, history: list[dict[str, str]]
) -> str | None:
    return _post_grok(_grok_messages(paper, question, history))


def _author_local(paper: dict[str, Any]) -> str:
    status = str(paper.get("status") or "")
    issues = paper.get("issues") or []
    label = paper.get("title") or paper.get("arxiv_id") or "This paper"
    ident = paper.get("arxiv_id") or ""
    if status in {"queued", "running"}:
        if status == "queued":
            return f"{label} ({ident}) is still queued."
        return "The read has not finished yet. Ask again when the stored read is ready."
    if not paper.get("paper_text") and not issues:
        return f"{label} ({ident}) is still queued."
    if not issues:
        return f"{label} ({ident}) has nothing to report."
    lines = [
        f"{label} ({ident}) {issue['issue_type']}: {issue['reason']}"
        for issue in issues
    ]
    return "\n".join(lines)


def ask_author_paper(job_id: str, question: str) -> dict[str, Any]:
    asked = question.strip()
    if not asked:
        raise BatchError(400, "question is empty")
    if not _on_shelf(job_id):
        raise BatchError(404, "paper not found")
    paper = paper_desk(job_id)
    if paper.get("conference_id") == DEMO_CONFERENCE_ID:
        raise BatchError(404, "paper not found")

    history = _load_history(job_id, limit=12)

    def grok(_conference: str, q: str, papers: list[dict[str, Any]]) -> str | None:
        return _author_grok(papers[0], q, history)

    def local(papers: list[dict[str, Any]]) -> str:
        return _author_local(papers[0])

    answer, action = voice.finish(
        asked, [paper], grok, local, str(paper.get("title") or paper["arxiv_id"])
    )
    trace, quotes = _reading([paper], answer)
    _store_exchange(job_id, asked, answer, quotes, trace)
    return {
        "answer": answer,
        "quotes": quotes,
        "trace": trace,
        "action": action,
    }
