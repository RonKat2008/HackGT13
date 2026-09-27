from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

import httpx

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
JEV_MODEL = "typesafe/jev-1.13"
DEFAULT_CAP = 40
_TIMEOUT = httpx.Timeout(20.0)
_CLIENT_LOCK = threading.Lock()
_CLIENT: httpx.Client | None = None

QUESTIONS: dict[str, Any] = {
    "verdict": {
        "type": "choice",
        "instructions": "How does the source relate to the claim?",
        "criteria": {
            "supported": "Source supports the claim",
            "contradicted": "Source contradicts the claim",
            "not_mentioned": "Source does not mention the claim",
        },
    },
    "confidence": {
        "type": "score",
        "instructions": "Confidence in this verification",
        "criteria": [
            "Low — indirect or partial evidence",
            "Medium — plausible alignment with gaps",
            "High — explicit support or contradiction",
        ],
    },
}

_NOT_RUN: dict[str, Any] = {
    "label": "not_mentioned",
    "confidence": 0.0,
    "probs": {},
    "not_run": True,
}


def jev_calls_left(calls_so_far: int, cap: int = DEFAULT_CAP) -> bool:
    return calls_so_far < cap


def cache_key(claim_text: str, source_text: str) -> str:
    claim_hash = hashlib.sha256(claim_text.encode()).hexdigest()
    evidence_hash = hashlib.sha256(source_text.encode()).hexdigest()
    body = f"{claim_hash}\n{evidence_hash}\n{JEV_MODEL}"
    return hashlib.sha256(body.encode()).hexdigest()


def _shared_client() -> httpx.Client:
    global _CLIENT
    with _CLIENT_LOCK:
        if _CLIENT is None:
            _CLIENT = httpx.Client(timeout=_TIMEOUT)
        return _CLIENT


def judge_claim(
    claim_text: str,
    source_text: str,
    transport: httpx.BaseTransport | None = None,
    api_key: str | None = None,
) -> dict:
    key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY", "")
    key_hash = cache_key(claim_text, source_text)
    cached = _read_cache(key_hash)
    if cached is not None:
        return cached

    payload = {
        "model": JEV_MODEL,
        "state": {"claim": claim_text, "source_text": source_text},
        "questions": QUESTIONS,
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    owns = transport is not None
    client = httpx.Client(transport=transport, timeout=_TIMEOUT) if owns else _shared_client()
    try:
        response = client.post(DECISIONS_URL, headers=headers, json=payload)
    except httpx.RequestError:
        return dict(_NOT_RUN)
    finally:
        if owns:
            client.close()

    if response.status_code != 200:
        return dict(_NOT_RUN)

    try:
        data = response.json()
    except ValueError:
        data = {}
    result = _map_success(data)
    _write_cache(
        key_hash,
        str(result["label"]),
        float(result["confidence"]),
        result.get("probs") if isinstance(result.get("probs"), dict) else {},
    )
    return result


def _map_success(data: Any) -> dict:
    payload = data if isinstance(data, dict) else {}
    answers = payload.get("answers")
    answers = answers if isinstance(answers, dict) else {}
    verdict = answers.get("verdict")
    verdict = verdict if isinstance(verdict, dict) else {}
    confidence_obj = answers.get("confidence")
    confidence_obj = confidence_obj if isinstance(confidence_obj, dict) else {}

    label = verdict.get("choice")
    if not isinstance(label, str) or not label:
        label = payload.get("label")
    if not isinstance(label, str) or not label:
        label = "not_mentioned"

    score = _as_confidence(confidence_obj.get("score"))
    if score is None:
        score = _as_confidence(payload.get("confidence"))
    if score is None:
        score = 0.0

    probs = verdict.get("probs")
    if not isinstance(probs, dict):
        probs = payload.get("probs")
    if not isinstance(probs, dict):
        probs = {}

    return {
        "label": label,
        "confidence": score,
        "probs": probs,
        "not_run": False,
    }


def _as_confidence(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _read_cache(key: str) -> dict[str, Any] | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT label, confidence, probs_json FROM jev_cache WHERE cache_key = ?",
            (key,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    try:
        probs = json.loads(row["probs_json"])
    except (TypeError, ValueError):
        probs = {}
    if not isinstance(probs, dict):
        probs = {}
    return {
        "label": row["label"],
        "confidence": float(row["confidence"]),
        "probs": probs,
        "not_run": False,
    }


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
