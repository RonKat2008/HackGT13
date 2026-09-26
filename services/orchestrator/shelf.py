from __future__ import annotations

import csv
import hashlib
import os
from pathlib import Path
from typing import Any, Callable, Iterable


EMBED_DIM = 384
AI_FLAGS = {"1", "true"}
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "shelf_abstracts.csv"
REPO_ROOT = Path(__file__).resolve().parents[2]
KAGGLE_DOWNLOADS = REPO_ROOT / "kaggle" / "downloads"


def enabled() -> bool:
    return bool(os.environ.get("SUPABASE_URL"))


def record_event(job_id: str, specialist: str, state: str, detail: str) -> None:
    if not enabled():
        return


def save_batch(payload: dict) -> None:
    if not enabled():
        return


def _is_ai_generated(raw: object) -> bool:
    return str(raw).strip().lower() in AI_FLAGS


def load_rows(path: str | Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            text = (raw.get("abstract") or "").strip()
            if not text:
                continue
            rows.append(
                {
                    "title": (raw.get("title") or "").strip(),
                    "text": text,
                    "label": "ai" if _is_ai_generated(raw.get("is_ai_generated")) else "human",
                }
            )
    return rows


def cap_rows(rows: Iterable[dict], per_label: int = 400) -> list[dict]:
    counts: dict[str, int] = {}
    capped: list[dict] = []
    for row in rows:
        label = str(row.get("label") or "")
        if counts.get(label, 0) >= per_label:
            continue
        counts[label] = counts.get(label, 0) + 1
        capped.append(row)
    return capped


def _default_embedder(text: str) -> list[float]:
    vectors: list[float] = []
    seed = 0
    encoded = text.encode("utf-8")
    while len(vectors) < EMBED_DIM:
        digest = hashlib.sha256(seed.to_bytes(4, "big") + encoded).digest()
        for byte in digest:
            vectors.append((byte / 127.5) - 1.0)
            if len(vectors) == EMBED_DIM:
                break
        seed += 1
    return vectors


def embed_texts(
    texts: Iterable[str],
    embedder: Callable[[str], list[float]] | None = None,
) -> list[list[float]]:
    fn = embedder or _default_embedder
    return [fn(text) for text in texts]


def default_shelf_path() -> Path:
    if KAGGLE_DOWNLOADS.is_dir():
        found = sorted(KAGGLE_DOWNLOADS.glob("*.csv"))
        if found:
            return found[0]
    return FIXTURE_PATH


def _external_id(title: str, label: str) -> str:
    return hashlib.sha256(f"{title}{label}".encode("utf-8")).hexdigest()


def _supabase_ready() -> tuple[str, str] | None:
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        return None
    return url.rstrip("/"), key


def _post_reference_items(
    url: str,
    key: str,
    items: list[dict[str, Any]],
    client: Any | None,
) -> None:
    headers = {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    endpoint = f"{url}/rest/v1/reference_items?on_conflict=source,external_id"
    if client is not None:
        client.post(endpoint, headers=headers, json=items)
        return

    import httpx

    with httpx.Client() as owned:
        owned.post(endpoint, headers=headers, json=items)


def load_shelf(
    path: str | Path,
    embedder: Callable[[str], list[float]] | None = None,
    client: Any | None = None,
) -> list[dict[str, Any]]:
    rows = cap_rows(load_rows(path))
    vectors = embed_texts([row["text"] for row in rows], embedder)
    loaded: list[dict[str, Any]] = []
    for row, embedding in zip(rows, vectors):
        loaded.append(
            {
                "title": row["title"],
                "text": row["text"],
                "label": row["label"],
                "embedding": embedding,
            }
        )

    creds = _supabase_ready()
    if creds is None:
        return loaded

    url, key = creds
    items = [
        {
            "source": "mit-abstracts",
            "external_id": _external_id(row["title"], row["label"]),
            "title": row["title"],
            "abstract": row["text"],
            "label": row["label"],
            "embedding": "[" + ",".join(str(value) for value in row["embedding"]) + "]",
        }
        for row in loaded
    ]
    _post_reference_items(url, key, items, client)
    return loaded

