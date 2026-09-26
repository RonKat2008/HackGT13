"""Check a claimed improvement against the numbers in a paper's tables."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import fitz

POINT_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s+percentage\s+points|\bby\s+(\d+(?:\.\d+)?)\s+points\b",
    re.I,
)
PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%\s+over", re.I)
NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
OURS_RE = re.compile(r"\bours\b|\bour method\b|\bproposed\b", re.I)


def read_tables(path: str | Path) -> list[dict[str, Any]]:
    doc = fitz.open(path)
    found: list[dict[str, Any]] = []
    try:
        for index, page in enumerate(doc):
            try:
                finder = page.find_tables()
            except Exception:
                continue
            for table in getattr(finder, "tables", []) or []:
                try:
                    rows = table.extract()
                except Exception:
                    continue
                parsed = _rows(rows or [])
                if parsed:
                    found.append({"page": index + 1, "rows": parsed})
    finally:
        doc.close()
    return found


def annotate(path: str | Path, claims: list[dict[str, Any]]) -> None:
    tables = read_tables(path)
    if not tables:
        return
    for claim in claims:
        if str(claim.get("claim_type") or "") != "numerical_comparison":
            continue
        if claim.get("computation"):
            continue
        claimed, kind = _claimed(str(claim.get("text") or ""))
        if claimed is None:
            continue
        table = _nearest(tables, claim.get("page"))
        if table is None:
            continue
        scored = _score(table["rows"], kind, claimed)
        if scored is None:
            continue
        computed, formula, matched = scored
        claim["depth"] = "mathematical"
        claim["confidence"] = 1.0
        claim["computation"] = {
            "claim_id": str(claim.get("claim_id") or ""),
            "dataset_slug": "",
            "resolution": "match" if matched else "not_found",
            "spec": {"claimed": claimed, "computed": computed},
            "actual": computed,
            "expected": claimed,
            "status": "reproduced" if matched else "could_not_reproduce",
            "steps": ["Compared the claimed change with the table."],
            "log": "",
            "formula": formula,
        }
        claim["verdict"] = "supported" if matched else "contradicted"
        if not matched:
            claim["reason"] = f"The table gives {formula}, not {claimed:g}."
        steps = list(claim.get("steps") or [])
        steps.append("Compared the claimed change with the table.")
        claim["steps"] = steps


def _rows(raw_rows: list[list[Any]]) -> list[tuple[str, float]]:
    parsed: list[tuple[str, float]] = []
    for row in raw_rows:
        if not row:
            continue
        label = " ".join(str(row[0] or "").split())
        number = None
        for cell in row[1:]:
            match = NUMBER_RE.search(str(cell or "").replace(",", ""))
            if match:
                number = float(match.group(0))
        if label and number is not None and label.lower() not in {"method", "accuracy", "model"}:
            parsed.append((label, number))
    return parsed


def _claimed(text: str) -> tuple[float | None, str]:
    percent = PERCENT_RE.search(text)
    if percent:
        return float(percent.group(1)), "percent"
    points = POINT_RE.search(text)
    if points:
        token = points.group(1) or points.group(2)
        return float(token), "points"
    return None, ""


def _nearest(tables: list[dict[str, Any]], page: Any) -> dict[str, Any] | None:
    if not isinstance(page, int):
        return tables[0]
    return min(tables, key=lambda table: abs(int(table["page"]) - page))


def _score(rows: list[tuple[str, float]], kind: str, claimed: float) -> tuple[float, str, bool] | None:
    ours = [(label, value) for label, value in rows if OURS_RE.search(label)]
    others = [(label, value) for label, value in rows if not OURS_RE.search(label)]
    if not ours or not others:
        return None
    ours_value = ours[0][1]
    _baseline_label, baseline = max(others, key=lambda item: item[1])
    if kind == "percent":
        if baseline == 0:
            return None
        diff = (ours_value - baseline) / baseline * 100
    else:
        diff = ours_value - baseline
    computed = _shown(diff)
    formula = f"{_shown(ours_value):g} − {_shown(baseline):g} = {computed:g}"
    gap = abs(claimed - computed)
    scale = max(abs(claimed), 1.0)
    matched = gap <= 0.05 or gap / scale <= 0.01
    return computed, formula, matched


def _shown(value: float) -> float:
    rounded = round(value, 1)
    if abs(value - rounded) < 1e-6:
        return rounded
    return round(value, 4)
