"""Fast structured check. Lya sees a claim and evidence rows. It does not search."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from models import LYA_VERDICTS

CHAT_URL = "https://api.x.ai/v1/chat/completions"
DEFAULT_MODEL = "grok-4.6"
DEFAULT_THRESHOLD = 0.90

_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "lya_verdict",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "verdict": {
                    "type": "string",
                    "enum": ["supported", "contradicted", "not_mentioned", "ambiguous"],
                },
                "confidence": {"type": "number"},
            },
            "required": ["verdict", "confidence"],
            "additionalProperties": False,
        },
    },
}

_NOT_RUN = {"verdict": "not_checked", "confidence": 0.0, "not_run": True}


def model_id() -> str:
    return os.environ.get("LYA_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def threshold() -> float:
    raw = os.environ.get("LYA_THRESHOLD", str(DEFAULT_THRESHOLD))
    try:
        score = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_THRESHOLD
    return min(1.0, max(0.0, score))


def accepts(answer: dict[str, Any]) -> bool:
    """A verdict at or above the threshold is stored. A weak contradiction is not a finding."""
    if answer.get("not_run"):
        return False
    verdict = str(answer.get("verdict") or "")
    if verdict not in LYA_VERDICTS:
        return False
    score = _confidence(answer.get("confidence"))
    if verdict == "contradicted" and score < threshold():
        return False
    return score >= threshold()


def cache_key(claim_text: str, evidence: list[dict[str, Any]], model: str) -> str:
    body = claim_text + "\n" + evidence_text(evidence) + "\n" + model
    return hashlib.sha256(body.encode()).hexdigest()


def evidence_text(evidence: list[dict[str, Any]]) -> str:
    lines = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        page = item.get("page")
        prefix = f"[p.{page}] " if isinstance(page, int) else ""
        lines.append(prefix + str(item.get("text") or ""))
    return "\n".join(lines)


def judge_claim(
    claim_text: str,
    evidence: list[dict[str, Any]] | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    key = api_key if api_key is not None else os.environ.get("XAI_API_KEY", "").strip()
    if not key:
        return dict(_NOT_RUN)
    rows = list(evidence or [])
    model = model_id()
    key_hash = cache_key(claim_text, rows, model)
    cached = _read_cache(key_hash)
    if cached is not None:
        return cached
    user = f"Claim:\n{claim_text}\n\nEvidence:\n{evidence_text(rows) or '(none)'}"
    try:
        with httpx.Client(transport=transport, timeout=30) as client:
            response = client.post(
                CHAT_URL,
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Compare the claim with the evidence rows only. "
                                "Return verdict and confidence. Do not search, write code, or parse a PDF."
                            ),
                        },
                        {"role": "user", "content": user},
                    ],
                    "response_format": _SCHEMA,
                },
            )
    except httpx.HTTPError:
        return dict(_NOT_RUN)
    if response.status_code != 200:
        return dict(_NOT_RUN)
    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError):
        return dict(_NOT_RUN)
    parsed = _parse(content)
    if parsed is None:
        return dict(_NOT_RUN)
    _write_cache(key_hash, parsed["verdict"], parsed["confidence"])
    return parsed


def _parse(content: str) -> dict[str, Any] | None:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    verdict = str(data.get("verdict") or "").strip().lower()
    if verdict not in LYA_VERDICTS:
        return None
    return {"verdict": verdict, "confidence": _confidence(data.get("confidence")), "not_run": False}


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
            "SELECT verdict, confidence FROM lya_cache WHERE cache_key = ?",
            (key,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {"verdict": row["verdict"], "confidence": float(row["confidence"]), "not_run": False}


def _write_cache(key: str, verdict: str, score: float) -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO lya_cache (cache_key, verdict, confidence, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                verdict = excluded.verdict,
                confidence = excluded.confidence
            """,
            (key, verdict, score, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def _connect():
    from store import connect, default_db_path

    conn = connect(default_db_path())
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lya_cache (
            cache_key TEXT PRIMARY KEY,
            verdict TEXT NOT NULL,
            confidence REAL NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    return conn
