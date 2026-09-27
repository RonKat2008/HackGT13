"""Resolve a dataset mention to one public table, or refuse to guess."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import jev
import store
import repro
from dsl import Spec

REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE = REPO_ROOT / ".arxiv-cache" / "datasets"

# Columns and row counts used to tell a named table from a lookalike.
CATALOG: dict[str, dict[str, Any]] = {
    "yasserh/titanic-dataset": {
        "title": "Titanic Dataset",
        "columns": [
            "PassengerId",
            "Survived",
            "Pclass",
            "Name",
            "Sex",
            "Age",
            "SibSp",
            "Parch",
            "Ticket",
            "Fare",
            "Cabin",
            "Embarked",
        ],
        "rows": 891,
    },
}

Search = Callable[[str], list[dict[str, Any]]]
Judge = Callable[[str, str], str | None]
TableFinder = Callable[[str, str], Path | None]
TableDownloader = Callable[[str, str], Path | None]

# One list call per slug for this process, including a timeout or an empty result.
_LOOKUP_CACHE: dict[str, list[dict[str, Any]]] = {}
_KAGGLE_WORD = re.compile(r"\bkaggle\b", re.I)
REPRO_ENGINE = "repro-1"
_CACHEABLE_STATUSES = frozenset({"reproduced", "could_not_reproduce"})
_SPEC_HASH_FIELDS = (
    "dataset_id",
    "file_id",
    "operation",
    "column",
    "filters",
    "arguments",
    "expected",
    "comparison",
)


def _normalize_slug(slug: str) -> str:
    return slug.strip().lower()


def _connect() -> sqlite3.Connection:
    conn = store.connect(store.default_db_path())
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dataset_tables (
            slug TEXT PRIMARY KEY,
            local_path TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS repro_cache (
            cache_key TEXT PRIMARY KEY,
            actual_json TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    return conn


def _csv_header_columns(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        row = next(csv.reader(handle), [])
    return [str(name).strip() for name in row]


def fingerprint_table(slug: str, path: Path) -> str | None:
    """Identify a local CSV by slug, size, mtime, and header columns only."""
    try:
        if not path.is_file():
            return None
        stat = path.stat()
        columns = _csv_header_columns(path)
    except OSError:
        return None
    raw = json.dumps(
        {
            "slug": _normalize_slug(slug),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "columns": columns,
        },
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def repro_spec_hash(spec: Any) -> str:
    if hasattr(spec, "model_dump"):
        payload = spec.model_dump(mode="json")
    elif isinstance(spec, dict):
        payload = spec
    else:
        raise TypeError("spec must be a ReproSpec")
    body = {key: payload.get(key) for key in _SPEC_HASH_FIELDS}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def repro_result_key(fingerprint: str, spec_digest: str) -> str:
    body = f"{fingerprint}\n{spec_digest}\n{REPRO_ENGINE}"
    return hashlib.sha256(body.encode()).hexdigest()


def lookup_repro_result(cache_key: str) -> dict[str, Any] | None:
    if not cache_key:
        return None
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT actual_json, status FROM repro_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    try:
        actual = json.loads(row["actual_json"])
    except (TypeError, json.JSONDecodeError):
        return None
    return {"actual": actual, "status": str(row["status"])}


def remember_repro_result(cache_key: str, actual: Any, status: str) -> None:
    if not cache_key or status not in _CACHEABLE_STATUSES:
        return
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO repro_cache (cache_key, actual_json, status, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                actual_json = excluded.actual_json,
                status = excluded.status,
                created_at = excluded.created_at
            """,
            (cache_key, json.dumps(actual), status, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def _under_download_roots(path: Path, slug: str) -> bool:
    """A default acquire only reuses files in the download folders find_table already searches."""
    resolved = path.resolve()
    roots = [
        Path(repro.DOWNLOADS).resolve(),
        (repro.REPO_ROOT / "services" / "orchestrator" / ".arxiv-cache" / "datasets" / slug.replace("/", "__")).resolve(),
    ]
    return any(resolved == root or root in resolved.parents for root in roots)


def lookup_table(slug: str) -> Path | None:
    key = _normalize_slug(slug)
    if not key:
        return None
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT local_path FROM dataset_tables WHERE slug = ?",
            (key,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    path = Path(str(row["local_path"]))
    if path.is_file():
        return path
    return None


def remember_table(slug: str, path: Path) -> None:
    key = _normalize_slug(slug)
    if not key or not path.is_file():
        return
    resolved = path.resolve()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO dataset_tables (slug, local_path, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
                local_path = excluded.local_path,
                created_at = excluded.created_at
            """,
            (key, str(resolved), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def acquire_table(
    slug: str,
    file_name: str = "",
    *,
    find: TableFinder | None = None,
    download: TableDownloader | None = None,
) -> Path | None:
    key = _normalize_slug(slug)
    if not key:
        return None
    finder = find if find is not None else repro.find_table
    table = finder(key, file_name)
    if table is not None:
        remember_table(key, table)
        return table
    cached = lookup_table(key)
    if cached is not None and (
        find is not None or download is not None or _under_download_roots(cached, key)
    ):
        return cached
    if download is None and find is None and key not in CATALOG:
        return None
    downloader = download if download is not None else repro.download_table
    table = downloader(key, file_name)
    if table is not None:
        remember_table(key, table)
    return table


def _candidate(slug: str, title: str = "", columns: list[str] | None = None, rows: int | None = None) -> dict[str, Any]:
    known = CATALOG.get(slug, {})
    return {
        "slug": slug,
        "title": title or str(known.get("title") or slug),
        "columns": list(columns if columns is not None else known.get("columns") or []),
        "rows": rows if rows is not None else known.get("rows"),
    }


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    cleaned = [part.strip() for part in parts if part.strip()]
    return cleaned or ([text.strip()] if text.strip() else [])


def _slug_needs_kaggle(sentence: str, slug: str) -> bool:
    """A catalog table is enough. Any other owner/name must sit in a sentence that says Kaggle."""
    if slug in CATALOG:
        return True
    left, _, right = slug.partition("/")
    if left.isdigit() or right.isdigit():
        return False
    return _KAGGLE_WORD.search(sentence) is not None


def names_public_table(text: str) -> bool:
    """True when a later Kaggle call could rerun a table this text actually names."""
    return bool(_mentions(text))


def _mentions(text: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sentence in _sentences(text):
        for match in repro.SLUG_RE.finditer(sentence):
            slug = match.group(1).lower()
            if slug in seen or not _slug_needs_kaggle(sentence, slug):
                continue
            seen.add(slug)
            found.append(_candidate(slug))
    lowered = text.lower()
    for name, slug in repro.KNOWN_DATASETS.items():
        if name in lowered and slug not in seen:
            seen.add(slug)
            found.append(_candidate(slug))
    return found


def _needed_columns(specs: list[Spec]) -> set[str]:
    return {spec.column for spec in specs if spec.column}


def _rows_expected(specs: list[Spec]) -> int | None:
    for spec in specs:
        if spec.operation.value == "ROWS" and isinstance(spec.expected, int):
            return spec.expected
    return None


def _has_columns(candidate: dict[str, Any], needed: set[str]) -> bool:
    if not needed:
        return True
    columns = {str(name) for name in candidate.get("columns") or []}
    return bool(columns) and needed <= columns


def _score(candidate: dict[str, Any], *, needed: set[str], rows_expected: int | None, explicit: set[str]) -> int:
    score = 0
    if candidate["slug"] in explicit:
        score += 2
    if _has_columns(candidate, needed):
        score += 2
    rows = candidate.get("rows")
    if rows_expected is not None and rows == rows_expected:
        score += 1
    return score


def _lookup_once(query: str) -> list[dict[str, Any]]:
    key = query.strip().lower()
    if key in _LOOKUP_CACHE:
        return _LOOKUP_CACHE[key]
    found = _kaggle_search(query)
    _LOOKUP_CACHE[key] = found
    return found


def _kaggle_search(query: str) -> list[dict[str, Any]]:
    if not os.environ.get("KAGGLE_USERNAME", "").strip() or not os.environ.get("KAGGLE_KEY", "").strip():
        return []
    digest = hashlib.sha256(query.lower().encode()).hexdigest()[:16]
    path = CACHE / f"search-{digest}.json"
    if path.is_file():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cached = None
        if isinstance(cached, list):
            return cached
    try:
        completed = subprocess.run(
            ["kaggle", "datasets", "list", "-s", query, "--csv"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0 or not completed.stdout.strip():
        return []
    rows = list(csv.DictReader(io.StringIO(completed.stdout)))
    found: list[dict[str, Any]] = []
    for row in rows:
        slug = str(row.get("ref") or row.get("id") or "").strip().lower()
        if "/" not in slug:
            continue
        found.append(_candidate(slug, title=str(row.get("title") or slug)))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(found), encoding="utf-8")
    except OSError:
        pass
    return found


def _default_judge(mention: str, title: str) -> str | None:
    if not os.environ.get("OPENROUTER_API_KEY", "").strip():
        return None
    judged = jev.judge_claim(
        f"Does this candidate represent the dataset in the paper?\n{mention}",
        title,
    )
    if judged.get("not_run"):
        return None
    if judged.get("label") == "supported":
        return "match"
    return "no_match"


def resolve(
    text: str,
    specs: list[Spec] | None = None,
    *,
    search: Search | None = None,
    judge: Judge | None = None,
) -> dict[str, Any]:
    specs = list(specs or [])
    needed = _needed_columns(specs)
    rows_expected = _rows_expected(specs)
    named = _mentions(text)
    explicit = {item["slug"] for item in named if repro.SLUG_RE.search(text) and item["slug"] in text.lower()}
    steps: list[str] = []
    if named:
        steps.append("Identified dataset")
    query = named[0]["slug"] if named else ""
    if not query:
        for name in repro.KNOWN_DATASETS:
            if name in text.lower():
                query = name
                break
    if search is not None:
        extra = search(query or text[:120])
    else:
        extra = []
    by_slug: dict[str, dict[str, Any]] = {}
    for item in [*named, *extra]:
        slug = str(item.get("slug") or "")
        if slug:
            by_slug.setdefault(slug, item)
    candidates = list(by_slug.values())
    fitting = [item for item in candidates if _has_columns(item, needed)]
    pool = fitting or ([] if needed else candidates)

    def finish(resolution: str, slug: str, step: str) -> dict[str, Any]:
        if step:
            steps.append(step)
        return {
            "resolution": resolution,
            "dataset_slug": slug,
            "steps": steps,
            "log": step,
        }

    if not pool:
        return finish("not_found", "", "")
    if len(pool) == 1:
        return finish("match", pool[0]["slug"], "Resolved exact dataset")

    scored = [
        (_score(item, needed=needed, rows_expected=rows_expected, explicit=explicit), item) for item in pool
    ]
    best = max(score for score, _item in scored)
    tied = [item for score, item in scored if score == best]
    if len(tied) == 1:
        return finish("match", tied[0]["slug"], "Resolved exact dataset")
    if len(tied) == 2:
        decide = judge if judge is not None else _default_judge
        picks = []
        for item in tied:
            try:
                label = decide(text, str(item.get("title") or item["slug"]))
            except Exception:
                label = None
            if label == "match":
                picks.append(item)
        if len(picks) == 1:
            return finish("match", picks[0]["slug"], "Resolved exact dataset")
    return finish("ambiguous", "", "Exact dataset version could not be verified")
