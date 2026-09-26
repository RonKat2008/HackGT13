"""Judge numerical and semantic claims with Jev, and remember the answer."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

import jev
from jev import DEFAULT_CAP

JUDGED_TYPES = {"numerical", "numerical_comparison", "semantic"}
NUMBER_RE = re.compile(r"\d+\.\d+")
_POOL_WORKERS = 4
_CACHE_LOCK = threading.Lock()


def cache_key(claim_text: str, source_text: str) -> str:
    return hashlib.sha256((claim_text + source_text).encode()).hexdigest()


def build_source_text(claim: dict[str, Any]) -> str:
    evidence = list(claim.get("evidence") or [])
    ordered = (
        [item for item in evidence if item.get("role") == "supports"]
        + [item for item in evidence if item.get("role") == "contradicts"]
        + [item for item in evidence if item.get("role") not in {"supports", "contradicts"}]
    )
    lines = [_tagged(item) for item in ordered]
    other_sections = "\n".join(
        _tagged(item)
        for item in ordered
        if str(item.get("section") or "") != str(claim.get("section") or "")
    )
    kind = str(claim.get("claim_type") or "")
    if kind in {"numerical", "numerical_comparison"}:
        missing = [
            token
            for token in NUMBER_RE.findall(str(claim.get("text") or ""))
            if token not in other_sections
        ]
        if missing:
            lines.append("Missing: " + ", ".join(missing))
    elif not evidence:
        lines.append("Missing: no supporting passage was retrieved.")
    return "\n".join(lines)


def finished_sentence(claims: list[dict[str, Any]]) -> str:
    judged = 0
    unconfigured = 0
    for claim in claims:
        steps = [str(step) for step in (claim.get("steps") or [])]
        if any(step == "Jev judgment" for step in steps):
            judged += 1
        elif any("Jev not configured" in step for step in steps):
            unconfigured += 1
    if judged:
        unit = "claim" if judged == 1 else "claims"
        return f"Judged {judged} {unit}."
    if unconfigured:
        return "Jev not configured."
    return "No numerical or semantic claim was sent to Jev."


def judge_claims(claims: list[dict[str, Any]]) -> None:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    judged = [
        claim
        for claim in claims
        if str(claim.get("claim_type") or "") in JUDGED_TYPES
    ]
    if not key:
        for claim in judged:
            _append_step(claim, "Jev not configured")
        return

    to_run = judged[:DEFAULT_CAP]

    def one(claim: dict[str, Any]) -> None:
        source = build_source_text(claim)
        key_hash = cache_key(str(claim.get("text") or ""), source)
        with _CACHE_LOCK:
            cached = _read_cache(key_hash)
        if cached is not None:
            _apply(claim, cached["label"], cached["confidence"])
            return
        answer = jev.judge_claim(str(claim.get("text") or ""), source, api_key=key)
        if answer.get("not_run"):
            claim["verdict"] = "not_checked"
            claim["confidence"] = 0.0
            return
        label = str(answer.get("label") or "not_mentioned")
        if label not in {"supported", "contradicted", "not_mentioned"}:
            label = "not_checked"
        score = _confidence(answer.get("confidence"))
        _apply(claim, label, score)
        with _CACHE_LOCK:
            _write_cache(
                key_hash,
                label,
                score,
                answer.get("probs") if isinstance(answer.get("probs"), dict) else {},
            )

    if not to_run:
        return
    with ThreadPoolExecutor(max_workers=_POOL_WORKERS) as pool:
        futures = [pool.submit(one, claim) for claim in to_run]
        for future in futures:
            future.result()


def _tagged(item: dict[str, Any]) -> str:
    text = str(item.get("text") or "")
    page = item.get("page")
    if isinstance(page, int):
        return f"[p.{page}] {text}".strip()
    return text


def _apply(claim: dict[str, Any], label: str, score: float) -> None:
    claim["verdict"] = label
    claim["confidence"] = score
    _append_step(claim, "Jev judgment")


def _append_step(claim: dict[str, Any], step: str) -> None:
    steps = list(claim.get("steps") or [])
    if step not in steps:
        steps.append(step)
    claim["steps"] = steps


def _confidence(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    score = float(value)
    if score > 1:
        score = score / 100
    return min(1.0, max(0.0, score))


def _read_cache(key: str) -> dict[str, Any] | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT label, confidence FROM jev_cache WHERE cache_key = ?",
            (key,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {"label": row["label"], "confidence": float(row["confidence"])}


def _write_cache(key: str, label: str, score: float, probs: dict[str, Any]) -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO jev_cache (cache_key, label, confidence, probs_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                label = excluded.label,
                confidence = excluded.confidence,
                probs_json = excluded.probs_json
            """,
            (key, label, score, json.dumps(probs), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def _connect():
    from store import connect, default_db_path

    conn = connect(default_db_path())
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
    return conn
