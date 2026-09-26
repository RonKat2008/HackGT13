"""Ask Crossref, OpenAlex, and Semantic Scholar whether a reference exists."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import quote

import httpx

import jev

USER_AGENT = "ArxAudit/0.1 (mailto:chair@arxaudit.local)"
TIMEOUT = 6.0
MATCH_SCORE = 0.85
WEAK_SCORE = 0.5
UNRESOLVED_REASON = "The reference could not be independently resolved in the catalogs searched."


def lookup(query: str, entry: dict[str, Any], transport: httpx.BaseTransport | None = None) -> dict[str, Any]:
    key = _cache_key(query)
    cached = _read_cache(key)
    if cached is not None:
        return cached
    queried = [
        _ask("crossref", _crossref_url(query), _crossref_candidates, entry, transport),
        _ask("openalex", _openalex_url(query), _openalex_candidates, entry, transport),
        _ask("semantic_scholar", _s2_url(query), _s2_candidates, entry, transport),
    ]
    catalog = {"reference": query, "queried": queried}
    if all(item["status"] != "error" for item in queried):
        _write_cache(key, catalog)
    return catalog


def decide(claim: dict[str, Any], catalog: dict[str, Any]) -> tuple[str, float, str]:
    queried = list(catalog.get("queried") or [])
    strong = [item for item in queried if item.get("status") == "match" and float(item.get("score") or 0) >= MATCH_SCORE]
    if strong:
        best = max(strong, key=lambda item: float(item.get("score") or 0))
        return "supported", min(1.0, float(best.get("score") or 0)), ""
    errors = [item for item in queried if item.get("status") == "error"]
    weak = [
        item
        for item in queried
        if WEAK_SCORE <= float(item.get("score") or 0) < MATCH_SCORE
    ]
    if weak and not errors:
        return _judge_weak(claim, max(weak, key=lambda item: float(item.get("score") or 0)))
    if errors:
        return "not_checked", 0.0, ""
    return "unresolved", 1.0, UNRESOLVED_REASON


def score_candidate(entry: dict[str, Any], candidate: dict[str, Any]) -> float:
    entry_doi = _doi(str(entry.get("doi") or ""))
    candidate_doi = _doi(str(candidate.get("doi") or ""))
    if entry_doi and candidate_doi and entry_doi == candidate_doi:
        return 1.0
    title_score = _title_score(str(entry.get("title") or ""), str(candidate.get("title") or ""))
    year_ok = _year_close(entry.get("year"), candidate.get("year"))
    authors_ok = _authors_overlap(entry.get("authors") or [], candidate.get("authors") or [])
    if title_score >= MATCH_SCORE and (year_ok or authors_ok):
        return max(title_score, 0.9)
    if title_score >= MATCH_SCORE:
        return title_score
    if authors_ok and year_ok:
        return 0.6
    return round(title_score * 0.5, 3)


def _ask(
    name: str,
    url: str,
    parse,
    entry: dict[str, Any],
    transport: httpx.BaseTransport | None,
) -> dict[str, Any]:
    try:
        with httpx.Client(transport=transport, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
            response = client.get(url)
    except httpx.RequestError:
        return _row(name, "error", "", "", 0.0)
    if response.status_code != 200:
        return _row(name, "error", "", "", 0.0)
    try:
        payload = response.json()
    except ValueError:
        return _row(name, "error", "", "", 0.0)
    best_title = ""
    best_doi = ""
    best_score = 0.0
    for candidate in parse(payload):
        scored = score_candidate(entry, candidate)
        if scored > best_score:
            best_score = scored
            best_title = str(candidate.get("title") or "")
            best_doi = str(candidate.get("doi") or "")
    status = "match" if best_score >= MATCH_SCORE else "no_match"
    return _row(name, status, best_title, best_doi, best_score)


def _row(catalog: str, status: str, title: str, doi: str, score: float) -> dict[str, Any]:
    return {
        "catalog": catalog,
        "status": status,
        "candidate_title": title,
        "doi": doi,
        "score": score,
    }


def _judge_weak(claim: dict[str, Any], item: dict[str, Any]) -> tuple[str, float, str]:
    if not os.environ.get("OPENROUTER_API_KEY", "").strip():
        return "ambiguous", float(item.get("score") or 0), ""
    source = " ".join(
        part
        for part in (
            str(item.get("candidate_title") or ""),
            str(item.get("doi") or ""),
            "Does this candidate represent the reference?",
        )
        if part
    )
    answer = jev.judge_claim(str(claim.get("text") or ""), source)
    if answer.get("not_run"):
        return "not_checked", 0.0, ""
    if answer.get("label") == "supported":
        return "supported", float(answer.get("confidence") or item.get("score") or 0), ""
    return "ambiguous", float(answer.get("confidence") or item.get("score") or 0), ""


def _crossref_url(query: str) -> str:
    return f"https://api.crossref.org/works?query.bibliographic={quote(query)}&rows=5"


def _openalex_url(query: str) -> str:
    return f"https://api.openalex.org/works?search={quote(query)}&per-page=5"


def _s2_url(query: str) -> str:
    return (
        "https://api.semanticscholar.org/graph/v1/paper/search"
        f"?query={quote(query)}&limit=5&fields=title,year,externalIds,authors"
    )


def _crossref_candidates(payload: Any) -> list[dict[str, Any]]:
    message = payload.get("message") if isinstance(payload, dict) else {}
    items = message.get("items") if isinstance(message, dict) else []
    return [_crossref_item(item) for item in items or [] if isinstance(item, dict)]


def _crossref_item(item: dict[str, Any]) -> dict[str, Any]:
    titles = item.get("title") if isinstance(item.get("title"), list) else []
    authors = []
    for author in item.get("author") or []:
        if isinstance(author, dict) and author.get("family"):
            authors.append(str(author["family"]))
    year = ""
    issued = item.get("issued") if isinstance(item.get("issued"), dict) else {}
    parts = issued.get("date-parts") if isinstance(issued, dict) else None
    if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
        year = str(parts[0][0])
    return {"title": titles[0] if titles else "", "doi": str(item.get("DOI") or ""), "year": year, "authors": authors}


def _openalex_candidates(payload: Any) -> list[dict[str, Any]]:
    results = payload.get("results") if isinstance(payload, dict) else []
    found = []
    for item in results or []:
        if not isinstance(item, dict):
            continue
        authors = []
        for authorship in item.get("authorships") or []:
            if not isinstance(authorship, dict):
                continue
            author = authorship.get("author") if isinstance(authorship.get("author"), dict) else {}
            name = str(author.get("display_name") or "")
            if name:
                authors.append(name.split()[-1])
        found.append(
            {
                "title": str(item.get("title") or ""),
                "doi": str(item.get("doi") or ""),
                "year": str(item.get("publication_year") or ""),
                "authors": authors,
            }
        )
    return found


def _s2_candidates(payload: Any) -> list[dict[str, Any]]:
    data = payload.get("data") if isinstance(payload, dict) else []
    found = []
    for item in data or []:
        if not isinstance(item, dict):
            continue
        external = item.get("externalIds") if isinstance(item.get("externalIds"), dict) else {}
        authors = []
        for author in item.get("authors") or []:
            if isinstance(author, dict) and author.get("name"):
                authors.append(str(author["name"]).split()[-1])
        found.append(
            {
                "title": str(item.get("title") or ""),
                "doi": str(external.get("DOI") or ""),
                "year": str(item.get("year") or ""),
                "authors": authors,
            }
        )
    return found


def _title_score(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, _plain(left), _plain(right)).ratio()


def _year_close(left: Any, right: Any) -> bool:
    try:
        return abs(int(left) - int(right)) <= 1
    except (TypeError, ValueError):
        return False


def _authors_overlap(left: list[Any], right: list[Any]) -> bool:
    wanted = {_plain(str(name)) for name in left if str(name).strip()}
    found = {_plain(str(name)) for name in right if str(name).strip()}
    return bool(wanted and found and wanted & found)


def _doi(value: str) -> str:
    cleaned = value.strip().lower()
    cleaned = re.sub(r"^https?://(dx\.)?doi\.org/", "", cleaned)
    return cleaned.rstrip(").,;")


def _plain(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def _cache_key(query: str) -> str:
    return hashlib.sha256(_plain(query).encode()).hexdigest()


def _read_cache(key: str) -> dict[str, Any] | None:
    conn = _connect()
    try:
        row = conn.execute("SELECT payload_json FROM catalog_cache WHERE cache_key = ?", (key,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    payload = json.loads(row["payload_json"])
    return payload if isinstance(payload, dict) else None


def _write_cache(key: str, catalog: dict[str, Any]) -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO catalog_cache (cache_key, payload_json, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET payload_json = excluded.payload_json
            """,
            (key, json.dumps(catalog), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def _connect():
    from store import connect, default_db_path

    conn = connect(default_db_path())
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS catalog_cache (
            cache_key TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    return conn
