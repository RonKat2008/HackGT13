"""Semantic retrieval over a paper: supporting passages and contradicting ones."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any, Callable

import fitz
import numpy as np

import claims as claim_extract
from shelf import EMBED_DIM, _default_embedder

CACHE_DIR = Path(__file__).resolve().parent / ".arxiv-cache" / "emb"
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
UNIT_RE = re.compile(r"%|percent|accuracy", re.I)


def _use_hash() -> bool:
    return os.environ.get("ARX_EMBEDDER", "").strip().lower() == "hash"


def _embedder() -> Callable[[str], list[float]]:
    if _use_hash():
        return _default_embedder
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return _default_embedder
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    def embed(text: str) -> list[float]:
        vector = model.encode(text, normalize_embeddings=True)
        return [float(value) for value in vector]

    return embed


def _cosine_matrix(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    query_norm = float(np.linalg.norm(query))
    row_norms = np.linalg.norm(matrix, axis=1)
    denom = row_norms * query_norm
    dots = matrix @ query
    scores = np.zeros(len(matrix), dtype=float)
    ok = denom > 0
    scores[ok] = dots[ok] / denom[ok]
    return scores


def _numbers(text: str) -> set[str]:
    return set(NUMBER_RE.findall(text))


def _units(text: str) -> set[str]:
    found = {match.group(0).lower() for match in UNIT_RE.finditer(text)}
    if "%" in text:
        found.add("%")
    return found


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
        self.vectors = _vectors(self.path, [chunk["text"] for chunk in self.chunks])

    def retrieve(
        self,
        claim_text: str,
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
        query = np.asarray(_embedder()(claim_text), dtype=float)
        matrix = self.vectors[np.asarray(chosen)]
        scores = _cosine_matrix(query, matrix)
        ranked = sorted(
            range(len(chosen)),
            key=lambda slot: (
                0 if prefer_conflicts and conflicts(claim_text, self.chunks[chosen[slot]]["text"]) else 1,
                -float(scores[slot]),
            ),
        )
        hits: list[dict[str, Any]] = []
        for slot in ranked[:k]:
            chunk = dict(self.chunks[chosen[slot]])
            chunk["score"] = float(scores[slot])
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
            for sentence in claim_extract.split_sentences(body):
                if sentence in seen:
                    continue
                seen.add(sentence)
                rows.append(
                    {
                        "page": claim_extract.find_page(doc, sentence),
                        "section": section,
                        "text": sentence,
                    }
                )
        return rows
    finally:
        doc.close()


def _vectors(path: Path, texts: list[str]) -> np.ndarray:
    if not texts:
        return np.zeros((0, EMBED_DIM), dtype=float)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    cache = CACHE_DIR / f"{digest}.npy"
    if cache.is_file() and not _use_hash():
        loaded = np.load(cache)
        if loaded.shape == (len(texts), loaded.shape[-1] if loaded.ndim == 2 else 0):
            if loaded.shape[0] == len(texts):
                return loaded
    embed = _embedder()
    matrix = np.asarray([embed(text) for text in texts], dtype=float)
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    if not _use_hash():
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        np.save(cache, matrix)
    return matrix


def attach(path: str | Path, sections: dict[str, str], typed_claims: list[dict[str, Any]]) -> None:
    index = PaperIndex(path, sections)
    for claim in typed_claims:
        if claim.get("claim_type") not in {"semantic", "numerical", "numerical_comparison"}:
            continue
        supporting = index.verifier(claim)
        contradicting = index.falsifier(claim)
        evidence: list[dict[str, Any]] = []
        for hit in supporting:
            evidence.append(_evidence_row(hit, "supports"))
        for hit in contradicting:
            evidence.append(_evidence_row(hit, "contradicts"))
        claim["evidence"] = evidence
        steps = list(claim.get("steps") or [])
        steps.append("Retrieved supporting evidence")
        steps.append("Searched for contradictory evidence")
        claim["steps"] = steps


def _evidence_row(hit: dict[str, Any], role: str) -> dict[str, Any]:
    return {
        "page": hit.get("page"),
        "section": hit.get("section") or "",
        "text": hit.get("text") or "",
        "role": role,
        "source": "paper",
    }
