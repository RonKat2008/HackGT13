"""Fast structured check. Lya sees a claim and evidence rows. It does not search."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

import httpx

from models import LYA_VERDICTS

CHAT_URL = "https://api.x.ai/v1/chat/completions"
DEFAULT_MODEL = "grok-4.6"
DEFAULT_THRESHOLD = 0.90
SYSTEM = (
    "Compare the claim with the evidence rows only. "
    "Return verdict and confidence. Do not search, write code, or parse a PDF."
)

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
_API_WORKERS = 4
_CACHE_LOCK = threading.Lock()


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
    if model == "local" or model.startswith("local:"):
        body += "\n" + _adapter_identity(model)
    return hashlib.sha256(body.encode()).hexdigest()


def _adapter_identity(model: str) -> str:
    from pathlib import Path

    from lya_local import ADAPTER_DIR

    raw = model.strip()
    if raw == "local":
        path = ADAPTER_DIR
    elif raw.startswith("local:"):
        path = Path(raw.split(":", 1)[1]).expanduser()
    else:
        return ""
    adapter = path / "adapters.safetensors"
    if adapter.is_file():
        return f"local{adapter.stat().st_mtime_ns}"
    return "local-missing-adapter"


def evidence_text(evidence: list[dict[str, Any]]) -> str:
    lines = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        page = item.get("page")
        section = str(item.get("section") or "").strip()
        tags = []
        if isinstance(page, int):
            tags.append(f"p.{page}")
        if section:
            tags.append(section)
        prefix = f"[{' '.join(tags)}] " if tags else ""
        lines.append(prefix + str(item.get("text") or ""))
    return "\n".join(lines)


def user_prompt(claim_text: str, evidence: list[dict[str, Any]]) -> str:
    return f"Claim:\n{claim_text}\n\nEvidence:\n{evidence_text(evidence) or '(none)'}"


def _judge_local(claim_text: str, rows: list[dict[str, Any]], model: str) -> dict[str, Any]:
    from lya_local import adapter_dir, generate

    path = adapter_dir(model)
    if path is None:
        return dict(_NOT_RUN)
    key_hash = cache_key(claim_text, rows, model)
    cached = _read_cache(key_hash)
    if cached is not None:
        return cached
    try:
        content = generate(path, SYSTEM, user_prompt(claim_text, rows))
    except (OSError, RuntimeError, ValueError):
        return dict(_NOT_RUN)
    parsed = _parse(content)
    if parsed is None:
        return dict(_NOT_RUN)
    _write_cache(key_hash, parsed["verdict"], parsed["confidence"])
    return parsed


def judge_claims(pairs: list[tuple[str, list[dict[str, Any]]]]) -> list[dict[str, Any]]:
    """Judge many claim/evidence pairs. Cache hits skip generation; local misses batch once."""
    if not pairs:
        return []
    model = model_id()
    results: list[dict[str, Any]] = [dict(_NOT_RUN) for _ in pairs]
    local_misses: list[tuple[int, str, list[dict[str, Any]], str]] = []
    api_misses: list[tuple[int, str, list[dict[str, Any]]]] = []

    for index, (claim_text, rows) in enumerate(pairs):
        key_hash = cache_key(claim_text, rows, model)
        cached = _read_cache(key_hash)
        if cached is not None:
            results[index] = cached
            continue
        if model == "local" or model.startswith("local:"):
            local_misses.append((index, claim_text, rows, key_hash))
        else:
            api_misses.append((index, claim_text, rows))

    if len(api_misses) <= 1:
        for index, claim_text, rows in api_misses:
            results[index] = judge_claim(claim_text, rows)
    else:
        workers = min(_API_WORKERS, len(api_misses))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                (index, pool.submit(judge_claim, claim_text, rows))
                for index, claim_text, rows in api_misses
            ]
            for index, future in futures:
                results[index] = future.result()

    if local_misses:
        from lya_local import adapter_dir, generate_many

        path = adapter_dir(model)
        if path is None:
            for index, _, _, _ in local_misses:
                results[index] = dict(_NOT_RUN)
        else:
            users = [user_prompt(claim_text, rows) for _, claim_text, rows, _ in local_misses]
            try:
                contents = generate_many(path, SYSTEM, users)
            except (OSError, RuntimeError, ValueError):
                contents = []
            for slot, (index, claim_text, rows, key_hash) in enumerate(local_misses):
                content = contents[slot] if slot < len(contents) else ""
                parsed = _parse(content)
                if parsed is None:
                    results[index] = dict(_NOT_RUN)
                else:
                    _write_cache(key_hash, parsed["verdict"], parsed["confidence"])
                    results[index] = parsed

    return results


def judge_claim(
    claim_text: str,
    evidence: list[dict[str, Any]] | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    rows = list(evidence or [])
    model = model_id()
    if model == "local" or model.startswith("local:"):
        return _judge_local(claim_text, rows, model)
    key = api_key if api_key is not None else os.environ.get("XAI_API_KEY", "").strip()
    if not key:
        return dict(_NOT_RUN)
    key_hash = cache_key(claim_text, rows, model)
    cached = _read_cache(key_hash)
    if cached is not None:
        return cached
    user = user_prompt(claim_text, rows)
    try:
        with httpx.Client(transport=transport, timeout=30) as client:
            response = client.post(
                CHAT_URL,
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": SYSTEM},
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
    with _CACHE_LOCK:
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
    with _CACHE_LOCK:
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
