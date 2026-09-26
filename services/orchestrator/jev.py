from __future__ import annotations

import os
from typing import Any

import httpx

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
JEV_MODEL = "typesafe/jev-1.13"
DEFAULT_CAP = 40

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


def judge_claim(
    claim_text: str,
    source_text: str,
    transport: httpx.BaseTransport | None = None,
    api_key: str | None = None,
) -> dict:
    key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY", "")
    payload = {
        "model": JEV_MODEL,
        "state": {"claim": claim_text, "source_text": source_text},
        "questions": QUESTIONS,
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(transport=transport) as client:
            response = client.post(DECISIONS_URL, headers=headers, json=payload)
    except httpx.RequestError:
        return dict(_NOT_RUN)

    if response.status_code != 200:
        return dict(_NOT_RUN)

    try:
        data = response.json()
    except ValueError:
        data = {}
    return _map_success(data)


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
