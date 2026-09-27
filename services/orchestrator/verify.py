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
from models import NUMBER_LOCK, Claim, deterministic_final
from playbook import apply as apply_patches
from roles import critic

JUDGED_TYPES = {"numerical", "numerical_comparison", "semantic"}
NUMBER_RE = re.compile(r"\d+\.\d+")
NUMBER_CHECK = NUMBER_LOCK
_POOL_WORKERS = 4
_CACHE_LOCK = threading.Lock()
_INDEX_LOCK = threading.Lock()
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
    lya_only = 0
    for claim in claims:
        steps = [str(step) for step in (claim.get("steps") or [])]
        jev_judged = any(step == "Jev judgment" for step in steps)
        lya_judged = any(step == "Lya verdict" for step in steps)
        if jev_judged:
            judged += 1
        elif any("Jev not configured" in step for step in steps):
            unconfigured += 1
        elif lya_judged:
            lya_only += 1
    if judged:
        unit = "claim" if judged == 1 else "claims"
        return f"Judged {judged} {unit}."
    if unconfigured:
        return "Jev not configured."
    if lya_only:
        unit = "claim" if lya_only == 1 else "claims"
        return f"Lya settled {lya_only} {unit}."
    return "No numerical or semantic claim was sent to Jev."


def critic_sentence(claims: list[dict[str, Any]]) -> str:
    reviewed = [
        claim
        for claim in claims
        if any(
            str(step).startswith("Round ") or str(step).startswith("Jev requested ")
            for step in (claim.get("steps") or [])
        )
    ]
    closed = [
        claim
        for claim in claims
        if any(str(step) == "Stopped after one judge pass" for step in (claim.get("steps") or []))
    ]
    if not reviewed and not closed:
        return "No uncertain verdict to review."
    if closed and not reviewed:
        count = len(closed)
        unit = "claim" if count == 1 else "claims"
        return f"Left {count} uncertain {unit} for a person."
    count = len(reviewed)
    unit = "claim" if count == 1 else "claims"
    return f"Reviewed {count} uncertain {unit}."


def close_uncertain(claims: list[dict[str, Any]]) -> None:
    """One judge pass is the budget. Claims still uncertain stop for a person."""
    for claim in claims:
        if deterministic_final(claim) or _number_contradicted(claim):
            continue
        if not _uncertain(claim):
            continue
        claim["verdict"] = "insufficient_evidence"
        claim["confidence"] = _confidence(claim.get("confidence"))
        claim["reason"] = "Requires human review"
        _append_step(claim, "Stopped after one judge pass")


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


def lya_model_off() -> bool:
    return os.environ.get("LYA_MODEL", "").strip().lower() == "off"


def lya_enabled() -> bool:
    if lya_model_off():
        return False
    if os.environ.get("PYTEST_CURRENT_TEST") and os.environ.get("ARX_LYA") != "live":
        return False
    return True


def judge_with_lya(
    claims: list[dict[str, Any]],
    *,
    path: str = "",
    sections: dict[str, str] | None = None,
    references: str = "",
) -> None:
    """Lya settles a routine claim. Jev runs only when Lya is unsure, then at most two tools."""
    if not lya_enabled():
        judge_claims(claims)
        return
    import lya

    context: dict[str, Any] = {
        "path": path,
        "sections": sections or {},
        "references": references,
        "index": None,
        "_index_tried": False,
    }
    openrouter = os.environ.get("OPENROUTER_API_KEY", "").strip()
    pending = [
        claim
        for claim in claims
        if str(claim.get("claim_type") or "") in JUDGED_TYPES and not deterministic_final(claim)
    ]
    capped = pending[:DEFAULT_CAP]
    pairs = [
        (str(claim.get("text") or ""), list(claim.get("evidence") or []))
        for claim in capped
    ]
    answers = lya.judge_claims(pairs)
    escalations: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for claim, answer in zip(capped, answers):
        if not answer.get("not_run") and lya.accepts(answer):
            _append_step(claim, "Lya verdict")
            _store(
                claim,
                str(answer.get("verdict") or "not_mentioned"),
                _confidence(answer.get("confidence")),
            )
            continue
        escalations.append((claim, answer))
    escalations.sort(key=lambda item: _jev_escalation_priority(item[0]))
    _run_escalations(escalations, context, openrouter, lya)


def _jev_escalation_priority(claim: dict[str, Any]) -> int:
    if _contradicted_looking(claim):
        return 0
    if _unresolved_citation_looking(claim):
        return 1
    return 2


def _contradicted_looking(claim: dict[str, Any]) -> bool:
    if deterministic_final(claim):
        return False
    evidence = list(claim.get("evidence") or [])
    if any(isinstance(item, dict) and item.get("role") == "contradicts" for item in evidence):
        return True
    reason = str(claim.get("reason") or "").lower()
    if "abstract" in reason and "number" in reason:
        return True
    if "number" in reason and "absent" in reason:
        return True
    return False


def _unresolved_citation_looking(claim: dict[str, Any]) -> bool:
    if _contradicted_looking(claim):
        return False
    if str(claim.get("verdict") or "") == "unresolved":
        return True
    catalog = claim.get("catalog")
    if isinstance(catalog, dict):
        queried = list(catalog.get("queried") or [])
        if queried and all(
            isinstance(item, dict) and str(item.get("status") or "") == "no_match"
            for item in queried
        ):
            return True
    return False


def _jev_after_lya(
    claim: dict[str, Any],
    answer: dict[str, Any],
    context: dict[str, Any],
    openrouter: str,
    lya: Any,
) -> None:
    if deterministic_final(claim):
        return
    if answer.get("not_run"):
        model = lya.model_id()
        if not os.environ.get("XAI_API_KEY", "").strip() and not (
            model == "local" or model.startswith("local:")
        ):
            _append_step(claim, "Lya not configured")
    else:
        _append_step(claim, "Lya verdict")
        if lya.accepts(answer):
            _store(claim, str(answer.get("verdict") or "not_mentioned"), _confidence(answer.get("confidence")))
            return
    if deterministic_final(claim):
        return
    if not openrouter:
        _append_step(claim, "Jev not configured")
        return
    _jev_once(claim, openrouter)
    if not _needs_more(claim):
        return
    if _jev_escalation_priority(claim) > 1:
        return
    claim["rounds"] = 1
    for round_num in range(2, MAX_ROUNDS + 1):
        import tools

        before = _evidence_key(claim)
        _ensure_index(context)
        names = tools.tools_for(claim)
        for name in names:
            _append_step(claim, f"Jev requested {name}")
        rows = tools.run_tools(claim, names, context)
        _merge_rows(claim, rows)
        claim["rounds"] = round_num
        if deterministic_final(claim):
            return
        if _evidence_key(claim) == before:
            return
        _jev_once(claim, openrouter)
        if not _needs_more(claim):
            return
    if _needs_more(claim):
        claim["verdict"] = "insufficient_evidence"
        claim["confidence"] = _confidence(claim.get("confidence"))
        claim["reason"] = "Requires human review"
        claim["rounds"] = MAX_ROUNDS


def _run_escalations(
    escalations: list[tuple[dict[str, Any], dict[str, Any]]],
    context: dict[str, Any],
    openrouter: str,
    lya: Any,
) -> None:
    """Same-priority claims share one Jev wave. A harder claim still finishes before an easier one starts."""
    band: list[tuple[dict[str, Any], dict[str, Any]]] = []
    band_key: int | None = None
    for item in escalations:
        key = _jev_escalation_priority(item[0])
        if band_key is None or key == band_key:
            band.append(item)
            band_key = key
            continue
        _run_band(band, context, openrouter, lya)
        band = [item]
        band_key = key
    if band:
        _run_band(band, context, openrouter, lya)


def _run_band(
    band: list[tuple[dict[str, Any], dict[str, Any]]],
    context: dict[str, Any],
    openrouter: str,
    lya: Any,
) -> None:
    def one(item: tuple[dict[str, Any], dict[str, Any]]) -> None:
        claim, answer = item
        _jev_after_lya(claim, answer, context, openrouter, lya)

    if len(band) <= 1:
        for item in band:
            one(item)
        return
    workers = min(_POOL_WORKERS, len(band))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one, item) for item in band]
        for future in futures:
            future.result()


def _ensure_index(context: dict[str, Any]) -> None:
    if context.get("index") is not None or context.get("_index_tried"):
        return
    with _INDEX_LOCK:
        if context.get("index") is not None or context.get("_index_tried"):
            return
        context["_index_tried"] = True
        _load_index(context)


def _load_index(context: dict[str, Any]) -> None:
    path = str(context.get("path") or "")
    if not path:
        return
    try:
        import evidence as evidence_index

        context["index"] = evidence_index.PaperIndex(path, context.get("sections") or {})
    except Exception:
        context["index"] = None


def _jev_once(claim: dict[str, Any], key: str) -> None:
    source = build_source_text(claim)
    key_hash = cache_key(str(claim.get("text") or ""), source)
    with _CACHE_LOCK:
        cached = _read_cache(key_hash)
    if cached is not None:
        _remember(claim, str(cached["label"]), float(cached["confidence"]))
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


def _needs_more(claim: dict[str, Any]) -> bool:
    if deterministic_final(claim):
        return False
    steps = [str(step) for step in (claim.get("steps") or [])]
    if "Jev judgment" not in steps:
        return False
    verdict = str(claim.get("verdict") or "")
    score = _confidence(claim.get("confidence"))
    if verdict == "not_mentioned":
        return True
    if verdict in {"supported", "contradicted", "ambiguous"} and score < REVIEW_CONFIDENCE:
        return True
    return False


def _evidence_key(claim: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(item.get("text") or "")
        for item in (claim.get("evidence") or [])
        if isinstance(item, dict)
    )


def _merge_rows(claim: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    import tools

    evidence = list(claim.get("evidence") or [])
    seen = {str(item.get("text") or "") for item in evidence if isinstance(item, dict)}
    for row in rows:
        item = tools.screen_evidence(row)
        if not item["text"] or item["text"] in seen:
            continue
        seen.add(item["text"])
        evidence.append(item)
    claim["evidence"] = evidence


def _store(claim: dict[str, Any], label: str, score: float) -> None:
    if deterministic_final(claim):
        return
    claim["verdict"] = label
    claim["confidence"] = score


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
