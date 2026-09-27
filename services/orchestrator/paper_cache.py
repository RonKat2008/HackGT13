"""Parsed-PDF cache keyed by sha256 of the file bytes. Same RUN_DB as the rest of the orchestrator."""

from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

import store

_CHUNK = 1024 * 1024


def file_hash(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def get(content_hash: str) -> dict[str, Any] | None:
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT text, sections_json, page_count, tables_json, references_json
            FROM paper_artifacts
            WHERE content_hash = ?
            """,
            (content_hash,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    sections = json.loads(row["sections_json"])
    tables = json.loads(row["tables_json"])
    references = json.loads(row["references_json"])
    return {
        "text": row["text"],
        "sections": sections if isinstance(sections, dict) else {},
        "page_count": int(row["page_count"]),
        "tables": tables if isinstance(tables, list) else [],
        "references": references if isinstance(references, list) else [],
    }


def put(
    content_hash: str,
    *,
    text: str,
    sections: dict[str, str],
    page_count: int,
    tables: list[dict[str, Any]],
    references: list[dict[str, Any]],
) -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO paper_artifacts (
                content_hash, text, sections_json, page_count,
                tables_json, references_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(content_hash) DO UPDATE SET
                text = excluded.text,
                sections_json = excluded.sections_json,
                page_count = excluded.page_count,
                tables_json = excluded.tables_json,
                references_json = excluded.references_json
            """,
            (
                content_hash,
                text,
                json.dumps(sections),
                int(page_count),
                json.dumps(tables),
                json.dumps(references),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def load_chunk_matrix(content_hash: str) -> tuple[np.ndarray, str, str] | None:
    """Return a stored chunk matrix for an existing paper-hash row, if one was saved."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT embeddings FROM paper_artifacts WHERE content_hash = ?",
            (content_hash,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    blob = row["embeddings"]
    if not blob:
        return None
    try:
        return _unpack_embeddings(blob)
    except Exception:
        return None


def store_chunk_matrix(
    content_hash: str,
    matrix: np.ndarray,
    *,
    embedder: str,
    fingerprint: str,
) -> None:
    """Write the chunk matrix onto an existing paper-hash row. Never inserts a row."""
    packed = _pack_embeddings(matrix, embedder, fingerprint)
    if packed is None:
        return
    conn = _connect()
    try:
        conn.execute(
            "UPDATE paper_artifacts SET embeddings = ? WHERE content_hash = ?",
            (packed, content_hash),
        )
        conn.commit()
    finally:
        conn.close()


def _pack_embeddings(matrix: np.ndarray, embedder: str, fingerprint: str) -> bytes | None:
    if embedder not in {"hash", "minilm"}:
        return None
    values = np.asarray(matrix, dtype=np.float64)
    if values.ndim != 2:
        return None
    meta = json.dumps({"embedder": embedder, "fingerprint": fingerprint}).encode("utf-8")
    body = io.BytesIO()
    np.save(body, values, allow_pickle=False)
    return len(meta).to_bytes(4, "big") + meta + body.getvalue()


def _unpack_embeddings(blob: bytes) -> tuple[np.ndarray, str, str]:
    size = int.from_bytes(blob[:4], "big")
    meta = json.loads(blob[4 : 4 + size].decode("utf-8"))
    embedder = str(meta.get("embedder") or "")
    fingerprint = str(meta.get("fingerprint") or "")
    if embedder not in {"hash", "minilm"}:
        raise ValueError("chunk matrix embedder tag is not hash or minilm")
    matrix = np.load(io.BytesIO(blob[4 + size :]), allow_pickle=False)
    if getattr(matrix, "ndim", 0) != 2:
        raise ValueError("chunk matrix must be 2-d")
    return np.asarray(matrix, dtype=np.float64), embedder, fingerprint


def _connect():
    conn = store.connect(store.default_db_path())
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS paper_artifacts (
            content_hash TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            sections_json TEXT NOT NULL,
            page_count INTEGER NOT NULL,
            tables_json TEXT NOT NULL,
            references_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            embeddings BLOB
        )
        """
    )
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(paper_artifacts)")}
    if "embeddings" not in columns:
        conn.execute("ALTER TABLE paper_artifacts ADD COLUMN embeddings BLOB")
        conn.commit()
    return conn
