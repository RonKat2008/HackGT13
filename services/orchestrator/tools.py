"""Tool allowlist over the checkers that already exist.

These functions gather evidence. They do not reimplement retrieval, tables,
catalogs, or the dataset executor.
"""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from models import TOOL_NAMES

_POOL_WORKERS = 4
_MUTATING = {"numeric_check", "execute_dataset_claim", "resolve_citation"}


def tools_for(claim: dict[str, Any]) -> list[str]:
    """At most two allowlisted tools, chosen from the claim type the regex already set."""
    kind = str(claim.get("claim_type") or "")
    if kind == "numerical_comparison":
        names = ["search_tables", "numeric_check"]
    elif kind == "numerical":
        names = ["search_paper", "search_section"]
    elif kind == "citation":
        names = ["resolve_citation"]
    elif kind == "dataset":
        names = ["resolve_dataset", "execute_dataset_claim"]
    else:
        names = ["search_paper", "search_section"]
    return [name for name in names if name in TOOL_NAMES][:2]


def run_tools(
    claim: dict[str, Any],
    names: list[str],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    chosen = [name for name in names if name in TOOL_NAMES][:2]
    read = [name for name in chosen if name not in _MUTATING]
    write = [name for name in chosen if name in _MUTATING]
    rows: list[dict[str, Any]] = []
    if len(read) > 1:
        with ThreadPoolExecutor(max_workers=_POOL_WORKERS) as pool:
            futures = [pool.submit(run_tool, name, claim, context) for name in read]
            for future in futures:
                rows.extend(future.result())
    else:
        for name in read:
            rows.extend(run_tool(name, claim, context))
    for name in write:
        rows.extend(run_tool(name, claim, context))
    return rows


def run_tool(name: str, claim: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    if name not in TOOL_NAMES:
        return []
    if name == "search_paper":
        return _search_paper(claim, context)
    if name == "search_section":
        return _search_section(claim, context)
    if name == "search_tables":
        return _search_tables(claim, context)
    if name == "numeric_check":
        return _numeric_check(claim, context)
    if name == "resolve_citation":
        return _resolve_citation(claim, context)
    if name == "resolve_dataset":
        return _resolve_dataset(claim, context)
    if name == "execute_dataset_claim":
        return _execute_dataset_claim(claim, context)
    return []


def screen_evidence(row: dict[str, Any]) -> dict[str, Any]:
    source_type = str(row.get("source_type") or "paper")
    source = {"catalog": "catalog", "dataset": "dataset", "computation": "computation"}.get(
        source_type,
        "paper",
    )
    return {
        "page": row.get("page") if isinstance(row.get("page"), int) else None,
        "section": str(row.get("section") or ""),
        "text": str(row.get("text") or ""),
        "role": "context",
        "source": source,
    }


def _search_paper(claim: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    index = context.get("index")
    if index is None:
        return []
    hits = index.verifier(claim, k=5)
    return [_from_hit(hit) for hit in hits]


def _search_section(claim: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    index = context.get("index")
    if index is None:
        return []
    current = str(claim.get("section") or "")
    section = "results" if current != "results" else "methods"
    hits = index.retrieve(str(claim.get("text") or ""), k=5, sections={section})
    return [_from_hit(hit, section=section) for hit in hits]


def _search_tables(claim: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    path = context.get("path") or ""
    if not path:
        return []
    import tables

    try:
        found = tables.read_tables(path)
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    needle = str(claim.get("text") or "")
    for table in found:
        lines = []
        for raw in table.get("rows") or []:
            lines.append(" | ".join(str(cell) for cell in raw))
        text = "\n".join(lines).strip()
        if not text:
            continue
        rows.append(
            _row(
                "table",
                text,
                page=table.get("page"),
                section="results",
                metadata={"claim_id": claim.get("claim_id"), "mentions_claim": needle[:80] in text},
            )
        )
    return rows


def _numeric_check(claim: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    path = context.get("path") or ""
    if not path:
        return []
    import tables

    try:
        tables.annotate(path, [claim])
    except Exception:
        return []
    computation = claim.get("computation") or {}
    if not isinstance(computation, dict) or not computation.get("formula"):
        return []
    return [
        _row(
            "computation",
            str(computation.get("formula") or ""),
            page=claim.get("page"),
            section="results",
            metadata={
                "status": computation.get("status"),
                "actual": computation.get("actual"),
                "expected": computation.get("expected"),
            },
        )
    ]


def _resolve_citation(claim: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    import references

    references.attach(
        [claim],
        str(context.get("references") or ""),
        transport=context.get("transport"),
    )
    catalog = claim.get("catalog") or {}
    if not isinstance(catalog, dict):
        return []
    rows = []
    for item in catalog.get("queried") or []:
        if not isinstance(item, dict):
            continue
        rows.append(
            _row(
                "catalog",
                str(item.get("candidate_title") or claim.get("text") or ""),
                section="references",
                metadata=item,
            )
        )
    if rows:
        return rows
    reference = str(catalog.get("reference") or "")
    if not reference:
        return []
    return [_row("catalog", reference, section="references", metadata={"reference": reference})]


def _resolve_dataset(claim: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    import compiler
    import datasets

    text = str(claim.get("text") or "")
    sections = context.get("sections") or {}
    specs = compiler.compile_claim(text, ask=lambda _text: [])
    blob = "\n".join(
        [text, *[str(sections.get(name) or "") for name in ("abstract", "methods", "results")]]
    )
    resolved = datasets.resolve(blob, specs, search=lambda _query: [])
    slug = str(resolved.get("dataset_slug") or "")
    return [
        _row(
            "dataset",
            slug or text,
            section="methods",
            metadata={
                "resolution": resolved.get("resolution"),
                "dataset_slug": slug,
                "steps": list(resolved.get("steps") or []),
            },
        )
    ]


def _execute_dataset_claim(claim: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    import repro

    sections = context.get("sections") or {}
    produced = repro.reproduce([claim], sections)
    rows: list[dict[str, Any]] = []
    for computation in produced:
        if not isinstance(computation, dict):
            continue
        status = str(computation.get("status") or "")
        if status in {"reproduced", "could_not_reproduce"}:
            claim["computation"] = computation
            claim["verdict"] = status
            claim["confidence"] = 1.0
        rows.append(
            _row(
                "dataset",
                str(computation.get("formula") or computation.get("log") or claim.get("text") or ""),
                section="results",
                metadata={
                    "status": status,
                    "actual": computation.get("actual"),
                    "expected": computation.get("expected"),
                    "formula": computation.get("formula"),
                },
            )
        )
    return rows


def _from_hit(hit: dict[str, Any], section: str | None = None) -> dict[str, Any]:
    return _row(
        "paper",
        str(hit.get("text") or ""),
        page=hit.get("page"),
        section=section if section is not None else str(hit.get("section") or ""),
        metadata={"score": hit.get("score")},
    )


def _row(
    source_type: str,
    text: str,
    *,
    page: Any = None,
    section: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    page_value = page if isinstance(page, int) else None
    body = str(text or "")
    digest = hashlib.sha256(f"{source_type}|{page_value}|{section}|{body}".encode()).hexdigest()[:16]
    return {
        "evidence_id": digest,
        "source_type": source_type,
        "page": page_value,
        "section": section,
        "text": body,
        "metadata": metadata or {},
    }
