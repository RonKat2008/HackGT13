"""Semantic retrieval over a paper: supporting passages and contradicting ones."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fitz
import numpy as np

import claims as claim_extract
import paper_cache
from shelf import EMBED_DIM, _default_embedder

_EVIDENCE_TYPES = frozenset({"semantic", "numerical", "numerical_comparison"})

CACHE_DIR = Path(__file__).resolve().parent / ".arxiv-cache" / "emb"
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
UNIT_RE = re.compile(r"%|percent|accuracy", re.I)


def _use_hash() -> bool:
    return os.environ.get("ARX_EMBEDDER", "").strip().lower() == "hash"


def _rank_by_overlap() -> bool:
    """Hash vectors do not carry meaning, so shared words decide the order."""
    return _use_hash() or _MINILM_FAILED


_MINILM: tuple[Any, Any] | None = None
_MINILM_FAILED = False


def _planned_mode() -> str:
    if _use_hash() or _MINILM_FAILED:
        return "hash"
    return "minilm"


def _embed_many(texts: list[str]) -> np.ndarray:
    """Embed a list in one call. Hash mode is one comprehension, not a model loop."""
    if not texts:
        return np.zeros((0, EMBED_DIM), dtype=float)
    if _use_hash() or not _ensure_minilm():
        return np.asarray([_default_embedder(text) for text in texts], dtype=float)
    return _minilm_matrix(texts)


def _embed_claim_texts(texts: list[str]) -> np.ndarray:
    return _embed_many(texts)


def _ensure_minilm() -> bool:
    global _MINILM, _MINILM_FAILED
    if _MINILM_FAILED:
        return False
    if _MINILM is None:
        loaded = _load_minilm()
        if loaded is None:
            _MINILM_FAILED = True
            return False
        _MINILM = loaded
    return True


def _minilm_matrix(texts: list[str]) -> np.ndarray:
    import torch

    tokenizer, model = _MINILM
    assert tokenizer is not None and model is not None
    tokens = tokenizer(
        [text or " " for text in texts],
        return_tensors="pt",
        truncation=True,
        max_length=256,
        padding=True,
    )
    with torch.no_grad():
        hidden = model(**tokens).last_hidden_state
        mask = tokens["attention_mask"].unsqueeze(-1).expand(hidden.size()).float()
        pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)
        pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
    return np.asarray(pooled.detach().cpu().numpy(), dtype=float)


def _load_minilm() -> tuple[Any, Any] | None:
    try:
        from transformers import AutoModel, AutoTokenizer

        name = "sentence-transformers/all-MiniLM-L6-v2"
        tokenizer = AutoTokenizer.from_pretrained(name)
        model = AutoModel.from_pretrained(name)
        model.eval()
        return tokenizer, model
    except Exception:
        return None


def _similarity_matrix(queries: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Cosine scores with shape [queries × chunks]."""
    queries = np.asarray(queries, dtype=float)
    matrix = np.asarray(matrix, dtype=float)
    if queries.ndim == 1:
        queries = queries.reshape(1, -1)
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    rows = int(queries.shape[0]) if queries.ndim == 2 else 0
    cols = int(matrix.shape[0]) if matrix.ndim == 2 else 0
    if rows == 0 or cols == 0 or int(queries.shape[-1]) == 0 or int(matrix.shape[-1]) == 0:
        return np.zeros((rows, cols), dtype=float)
    query_norms = np.linalg.norm(queries, axis=1, keepdims=True)
    row_norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    denom = query_norms @ row_norms.T
    dots = queries @ matrix.T
    scores = np.zeros(dots.shape, dtype=float)
    ok = denom > 0
    scores[ok] = dots[ok] / denom[ok]
    return scores


def _cosine_matrix(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    return _similarity_matrix(np.asarray(query, dtype=float).reshape(1, -1), matrix)[0]


def _numbers(text: str) -> set[str]:
    return set(NUMBER_RE.findall(text))


def _units(text: str) -> set[str]:
    found = {match.group(0).lower() for match in UNIT_RE.finditer(text)}
    if "%" in text:
        found.add("%")
    return found


def _overlap(left: str, right: str) -> int:
    words = _content_words(left)
    if not words:
        return 0
    return len(words & _content_words(right))


def _content_words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z]{4,}", text.lower())}


def conflicts(claim_text: str, chunk_text: str) -> bool:
    claim_numbers = _numbers(claim_text)
    chunk_numbers = _numbers(chunk_text)
    if not claim_numbers or not chunk_numbers or claim_numbers == chunk_numbers:
        return False
    return bool(_units(claim_text) & _units(chunk_text))


class PaperIndex:
    def __init__(self, path: str | Path, sections: dict[str, str]) -> None:
        self.path = Path(path)
        self.chunks = _chunks(self.path, sections)
        self.chunk_matrix = _vectors(self.path, [chunk["text"] for chunk in self.chunks])
        self.vectors = self.chunk_matrix

    def around(self, text: str, n: int = 2) -> list[dict[str, Any]]:
        target = -1
        needle = " ".join(text.split())[:160]
        for index, chunk in enumerate(self.chunks):
            body = chunk["text"]
            if body == text or (needle and needle in body):
                target = index
                break
        if target < 0:
            return []
        section = self.chunks[target]["section"]
        picked: list[dict[str, Any]] = []
        for index in range(target - n, target + n + 1):
            if index == target or index < 0 or index >= len(self.chunks):
                continue
            chunk = self.chunks[index]
            if chunk["section"] != section:
                continue
            picked.append(chunk)
        return picked

    def claim_similarity(self, claims: list[dict[str, Any]]) -> np.ndarray:
        """One [C × N] cosine matrix. Claim texts are embedded in a single batch."""
        texts = [str(claim.get("text") or "") for claim in claims]
        width = int(self.chunk_matrix.shape[0]) if self.chunk_matrix.ndim == 2 else 0
        if not texts:
            return np.zeros((0, width), dtype=float)
        return _similarity_matrix(_embed_claim_texts(texts), self.chunk_matrix)

    def retrieve(
        self,
        claim_text: str,
        k: int = 5,
        sections: set[str] | None = None,
        prefer_conflicts: bool = False,
    ) -> list[dict[str, Any]]:
        if not self.chunks or k <= 0:
            return []
        cached = _read_retrieval_cache(self.path, claim_text)
        if cached is not None:
            return cached
        row = _cosine_matrix(_embed_many([claim_text])[0], self.chunk_matrix)
        hits = self.hits_from_scores(
            claim_text,
            row,
            k=k,
            sections=sections,
            prefer_conflicts=prefer_conflicts,
        )
        _write_retrieval_cache(self.path, claim_text, hits)
        return hits

    def hits_from_scores(
        self,
        claim_text: str,
        scores: np.ndarray,
        k: int = 5,
        sections: set[str] | None = None,
        prefer_conflicts: bool = False,
    ) -> list[dict[str, Any]]:
        if not self.chunks or k <= 0:
            return []
        chosen = [
            index
            for index, chunk in enumerate(self.chunks)
            if chunk["text"] != claim_text and (sections is None or chunk["section"] in sections)
        ]
        if not chosen:
            return []
        picked = np.asarray(scores, dtype=float)[np.asarray(chosen)]
        ranked = sorted(
            range(len(chosen)),
            key=lambda slot: (
                0 if prefer_conflicts and conflicts(claim_text, self.chunks[chosen[slot]]["text"]) else 1,
                -_overlap(claim_text, self.chunks[chosen[slot]]["text"]) if _rank_by_overlap() else 0,
                -float(picked[slot]),
            ),
        )
        hits: list[dict[str, Any]] = []
        for slot in ranked[:k]:
            chunk = dict(self.chunks[chosen[slot]])
            chunk["score"] = float(picked[slot])
            hits.append(chunk)
        return hits

    def verifier(self, claim: dict[str, Any], k: int = 5) -> list[dict[str, Any]]:
        return self.retrieve(str(claim.get("text") or ""), k=k)

    def falsifier(self, claim: dict[str, Any], k: int = 5) -> list[dict[str, Any]]:
        section = str(claim.get("section") or "")
        others = {chunk["section"] for chunk in self.chunks if chunk["section"] != section}
        return self.retrieve(
            str(claim.get("text") or ""),
            k=k,
            sections=others or None,
            prefer_conflicts=True,
        )


def _chunks(path: Path, sections: dict[str, str]) -> list[dict[str, Any]]:
    doc = fitz.open(path)
    try:
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for section, body in claim_extract._sections_to_scan(sections, path):
            if section in claim_extract.SKIP_SECTIONS:
                continue
            for piece in claim_extract.evidence_pieces(body):
                if piece in seen:
                    continue
                seen.add(piece)
                rows.append(
                    {
                        "page": claim_extract.find_page(doc, piece),
                        "section": section,
                        "text": piece,
                    }
                )
        return rows
    finally:
        doc.close()


def _chunk_fingerprint(texts: list[str]) -> str:
    digest = hashlib.sha256()
    for text in texts:
        raw = text.encode("utf-8")
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    return digest.hexdigest()


def _cached_chunk_matrix(digest: str, texts: list[str], mode: str) -> np.ndarray | None:
    try:
        loaded = paper_cache.load_chunk_matrix(digest)
    except Exception:
        return None
    if loaded is None:
        return None
    matrix, embedder, fingerprint = loaded
    if embedder != mode or fingerprint != _chunk_fingerprint(texts):
        return None
    if matrix.ndim != 2 or matrix.shape[0] != len(texts):
        return None
    return np.asarray(matrix, dtype=float)


def _store_chunk_matrix(digest: str, texts: list[str], matrix: np.ndarray, mode: str) -> None:
    if mode not in {"hash", "minilm"} or matrix.ndim != 2 or matrix.shape[0] != len(texts):
        return
    try:
        paper_cache.store_chunk_matrix(
            digest,
            matrix,
            embedder=mode,
            fingerprint=_chunk_fingerprint(texts),
        )
    except Exception:
        return


def _vectors(path: Path, texts: list[str]) -> np.ndarray:
    if not texts:
        return np.zeros((0, EMBED_DIM), dtype=float)
    digest = paper_cache.file_hash(path)
    mode = _planned_mode()
    cached = _cached_chunk_matrix(digest, texts, mode)
    if cached is not None:
        return cached
    npy = CACHE_DIR / f"{digest}.npy"
    if npy.is_file() and mode != "hash":
        loaded = np.load(npy)
        if loaded.ndim == 2 and loaded.shape[0] == len(texts):
            matrix = np.asarray(loaded, dtype=float)
            _store_chunk_matrix(digest, texts, matrix, "minilm")
            return matrix
    matrix = _embed_many(texts)
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    actual = _planned_mode()
    if actual != "hash":
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        np.save(npy, matrix)
    _store_chunk_matrix(digest, texts, matrix, actual)
    return matrix


def attach(path: str | Path, sections: dict[str, str], typed_claims: list[dict[str, Any]]) -> None:
    index = PaperIndex(path, sections)
    targets = [claim for claim in typed_claims if claim.get("claim_type") in _EVIDENCE_TYPES]
    scores = index.claim_similarity(targets)
    for claim, row in zip(targets, scores):
        text = str(claim.get("text") or "")
        supporting = index.hits_from_scores(text, row, k=5)
        section = str(claim.get("section") or "")
        others = {chunk["section"] for chunk in index.chunks if chunk["section"] != section}
        contradicting = index.hits_from_scores(
            text,
            row,
            k=5,
            sections=others or None,
            prefer_conflicts=True,
        )
        evidence: list[dict[str, Any]] = []
        for hit in supporting:
            evidence.append(_evidence_row(hit, "supports"))
        for hit in contradicting:
            evidence.append(_evidence_row(hit, "contradicts"))
        claim["evidence"] = evidence
        claim["_neighbors"] = index.around(text, 6)
        merge_neighbors(claim)
        steps = list(claim.get("steps") or [])
        steps.append("Retrieved supporting evidence")
        steps.append("Searched for contradictory evidence")
        claim["steps"] = steps


def merge_neighbors(claim: dict[str, Any]) -> None:
    """The sentences beside a claim are evidence on the first pass, before Lya."""
    evidence = list(claim.get("evidence") or [])
    seen = {
        " ".join(str(item.get("text") or "").split())
        for item in evidence
        if isinstance(item, dict)
    }
    seen.add(" ".join(str(claim.get("text") or "").split()))
    for row in claim.get("_neighbors") or []:
        if not isinstance(row, dict):
            continue
        text = " ".join(str(row.get("text") or "").split())
        if not text or text in seen:
            continue
        seen.add(text)
        evidence.append(
            {
                "page": row.get("page") if row.get("page") is not None else claim.get("page"),
                "section": str(row.get("section") or claim.get("section") or ""),
                "text": text,
                "role": "context",
                "source": "paper",
            }
        )
    claim["evidence"] = evidence


def _evidence_row(hit: dict[str, Any], role: str) -> dict[str, Any]:
    return {
        "page": hit.get("page"),
        "section": hit.get("section") or "",
        "text": hit.get("text") or "",
        "role": role,
        "source": "paper",
    }


def _claim_hash(claim_text: str) -> str:
    return hashlib.sha256(claim_text.encode()).hexdigest()


def _retrieval_cache_key(paper_hash: str, claim_text: str) -> str:
    body = f"{paper_hash}\n{_claim_hash(claim_text)}"
    return hashlib.sha256(body.encode()).hexdigest()


def _read_retrieval_cache(path: Path, claim_text: str) -> list[dict[str, Any]] | None:
    if not path.is_file():
        return None
    try:
        paper_hash = paper_cache.file_hash(path)
    except OSError:
        return None
    key = _retrieval_cache_key(paper_hash, claim_text)
    conn = _retrieval_connect()
    try:
        row = conn.execute(
            "SELECT rows_json FROM retrieval_cache WHERE cache_key = ?",
            (key,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    try:
        loaded = json.loads(row["rows_json"])
    except (TypeError, ValueError):
        return None
    if not isinstance(loaded, list):
        return None
    return [dict(item) for item in loaded if isinstance(item, dict)]


def _write_retrieval_cache(path: Path, claim_text: str, rows: list[dict[str, Any]]) -> None:
    if not path.is_file():
        return
    try:
        paper_hash = paper_cache.file_hash(path)
    except OSError:
        return
    key = _retrieval_cache_key(paper_hash, claim_text)
    conn = _retrieval_connect()
    try:
        conn.execute(
            """
            INSERT INTO retrieval_cache (cache_key, rows_json, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                rows_json = excluded.rows_json
            """,
            (key, json.dumps(rows), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def _retrieval_connect():
    from store import connect, default_db_path

    conn = connect(default_db_path())
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS retrieval_cache (
            cache_key TEXT PRIMARY KEY,
            rows_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    return conn
