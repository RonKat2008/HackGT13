"""Judge numerical and semantic claims with Jev, and remember the answer."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from collections.abc import Callable
from typing import Any

import jev
from jev import DEFAULT_CAP
from loop import retry_guard_dropped
from models import Claim
from playbook import apply as apply_patches
from roles import critic

JUDGED_TYPES = {"numerical", "numerical_comparison", "semantic"}
NUMBER_RE = re.compile(r"\d+\.\d+")
NUMBER_CHECK = "Compared the abstract number with the results."
_POOL_WORKERS = 4
_CACHE_LOCK = threading.Lock()
REVIEW_CONFIDENCE = 0.70
MAX_ROUNDS = 3


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


def critic_sentence(claims: list[dict[str, Any]]) -> str:
    reviewed = [
        claim
        for claim in claims
        if any(str(step).startswith("Round ") for step in (claim.get("steps") or []))
    ]
    if not reviewed:
        return "No uncertain verdict to review."
    count = len(reviewed)
    unit = "claim" if count == 1 else "claims"
    return f"Reviewed {count} uncertain {unit}."


def review_uncertain(
    claims: list[dict[str, Any]],
    emit: Callable[[str], None] | None = None,
) -> None:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key or (os.environ.get("PYTEST_CURRENT_TEST") and os.environ.get("ARX_ROUNDS") != "live"):
        return
    for claim in claims:
        if _number_contradicted(claim) or not _uncertain(claim):
            continue
        original = str(claim.get("text") or "")
        claim["rounds"] = max(int(claim.get("rounds") or 0), 1)
        for round_num in range(claim["rounds"] + 1, MAX_ROUNDS + 1):
            legacy = _legacy_claim(claim)
            patch = critic(legacy, str(claim.get("verdict") or "not_mentioned"), ["evidence"])
            if retry_guard_dropped(original, legacy.text):
                continue
            _query, lines = apply_patches([patch], "evidence")
            neighbors = 1 if "neighbors:1" in lines else 2
            _widen(claim, neighbors)
            if retry_guard_dropped(original, str(claim.get("text") or "")):
                claim["text"] = original
            answer = jev.judge_claim(original, build_source_text(claim), api_key=key)
            claim["rounds"] = round_num
            _append_step(claim, f"Round {round_num}: widened to ±{neighbors} sentences")
            if emit is not None:
                emit(f"Round {round_num}: widened to ±{neighbors} sentences")
            if answer.get("not_run"):
                claim["verdict"] = "not_checked"
                claim["confidence"] = 0.0
                break
            label = str(answer.get("label") or "not_mentioned")
            if label not in {"supported", "contradicted", "not_mentioned"}:
                label = "not_checked"
            _apply(claim, label, _confidence(answer.get("confidence")))
            claim["text"] = original
            if not _uncertain(claim):
                break
        else:
            if _uncertain(claim) and str(claim.get("claim_type") or "") == "semantic":
                claim["verdict"] = "insufficient_evidence"
                claim["confidence"] = float(claim.get("confidence") or 0)
                claim["reason"] = "Requires human review"
                claim["rounds"] = MAX_ROUNDS


def _uncertain(claim: dict[str, Any]) -> bool:
    if str(claim.get("claim_type") or "") not in JUDGED_TYPES:
        return False
    steps = [str(step) for step in (claim.get("steps") or [])]
    if "Jev judgment" not in steps:
        return False
    verdict = str(claim.get("verdict") or "")
    if verdict == "not_mentioned":
        return True
    if verdict in {"supported", "contradicted"} and float(claim.get("confidence") or 0) < REVIEW_CONFIDENCE:
        return True
    return False


def _legacy_claim(claim: dict[str, Any]) -> Claim:
    evidence = claim.get("evidence") or []
    span = str(evidence[0].get("text") or "") if evidence else str(claim.get("text") or "")
    return Claim(
        id=str(claim.get("claim_id") or "claim"),
        text=str(claim.get("text") or "claim"),
        type=str(claim.get("claim_type") or "semantic"),
        evidence_span=span or "paper",
        source_id=str(claim.get("job_id") or "desk"),
        source_kind="paper",
    )


def _widen(claim: dict[str, Any], neighbors: int) -> None:
    evidence = list(claim.get("evidence") or [])
    window = list(claim.get("_neighbors") or [])[: max(neighbors, 0) * 2]
    for row in window:
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        evidence.append(
            {
                "page": row.get("page") if row.get("page") is not None else claim.get("page"),
                "section": str(row.get("section") or claim.get("section") or "results"),
                "text": text,
                "role": "context",
                "source": "paper",
            }
        )
    evidence.append(
        {
            "page": claim.get("page"),
            "section": str(claim.get("section") or "results"),
            "text": f"Neighbor window ±{neighbors} sentences around the claim.",
            "role": "context",
            "source": "paper",
        }
    )
    claim["evidence"] = evidence


def judge_claims(claims: list[dict[str, Any]]) -> None:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    judged = [
        claim
        for claim in claims
        if not claim.get("computation") and str(claim.get("claim_type") or "") in JUDGED_TYPES
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
            _remember(claim, cached["label"], cached["confidence"])
            return
        answer = jev.judge_claim(str(claim.get("text") or ""), source, api_key=key)
        if answer.get("not_run"):
            if not _number_contradicted(claim):
                claim["verdict"] = "not_checked"
                claim["confidence"] = 0.0
            return
        label = str(answer.get("label") or "not_mentioned")
        if label not in {"supported", "contradicted", "not_mentioned"}:
            label = "not_checked"
        score = _confidence(answer.get("confidence"))
        _remember(claim, label, score)
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


def _number_contradicted(claim: dict[str, Any]) -> bool:
    if str(claim.get("verdict") or "") != "contradicted":
        return False
    return any(NUMBER_CHECK in str(step) for step in (claim.get("steps") or []))


def _remember(claim: dict[str, Any], label: str, score: float) -> None:
    if _number_contradicted(claim) and label != "contradicted":
        _append_step(claim, "Jev judgment")
        return
    _apply(claim, label, score)


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
