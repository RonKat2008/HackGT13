"""Compile a dataset sentence into restricted DSL specs.

Patterns run first. A model may propose one JSON spec, which is accepted only
when it validates as ``dsl.Spec``. Model text is never executed.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from pydantic import ValidationError

import repro
from dsl import Operation, Spec

Ask = Callable[[str], str | None]

OF_RE = re.compile(
    r"\bof the\s+(\d[\d,]*)\s+[A-Za-z]+,\s+(\d[\d,]*)\s+([A-Za-z][A-Za-z ]{0,40})",
    re.I,
)
CLASS_RE = re.compile(
    r"\b(\d[\d,]*)\s+passengers\s+(?:travelled|traveled|were|are)\s+in\s+"
    r"(first|second|third)\s+class\b",
    re.I,
)
ROWS_RE = re.compile(
    r"\b(?:contains|has|with|of)\s+(\d[\d,]*)\s+"
    r"(rows|observations|passengers|samples|records)\b",
    re.I,
)
MEAN_RE = re.compile(
    r"\b(?:mean|average)\s+(?:of\s+)?([A-Za-z_][A-Za-z0-9_]*)\s+"
    r"(?:of|is|=)\s+(\d[\d,]*(?:\.\d+)?)\b",
    re.I,
)
VALUE_MAP = (
    (re.compile(r"\bfirst class\b", re.I), "Pclass", 1),
    (re.compile(r"\bsecond class\b", re.I), "Pclass", 2),
    (re.compile(r"\bthird class\b", re.I), "Pclass", 3),
    (re.compile(r"\bsurvived\b", re.I), "Survived", 1),
    (re.compile(r"\bdied\b|\bdid not survive\b", re.I), "Survived", 0),
)
CLASS_EQUALS = {"first": 1, "second": 2, "third": 3}

COMPILE_PROMPT = """Compile this dataset claim into one JSON object and nothing else.
Keys: operation, column, equals, numerator_equals, other_column, expected.
operation is one of ROWS, COUNT, COUNT_EQ, SUM, MEAN, MEDIAN, MIN, MAX, PERCENT, DIFFERENCE, PERCENT_CHANGE.
Do not write Python.
"""


def _number(token: str) -> int | float:
    cleaned = token.replace(",", "")
    if "." in cleaned:
        return float(cleaned)
    return int(cleaned)


def _value_column(text: str) -> tuple[str, int] | None:
    for pattern, column, equals in VALUE_MAP:
        if pattern.search(text):
            return column, equals
    return None


def dataset_slug(text: str) -> str | None:
    match = repro.SLUG_RE.search(text)
    if match:
        return match.group(1).lower()
    lowered = text.lower()
    for name, slug in repro.KNOWN_DATASETS.items():
        if name in lowered:
            return slug
    return None


def _patterns(text: str) -> list[Spec]:
    specs: list[Spec] = []
    of = OF_RE.search(text)
    if of:
        specs.append(Spec(operation=Operation.ROWS, expected=_number(of.group(1))))
        mapped = _value_column(of.group(3))
        if mapped:
            column, equals = mapped
            specs.append(
                Spec(
                    operation=Operation.COUNT_EQ,
                    column=column,
                    equals=equals,
                    expected=_number(of.group(2)),
                )
            )
        return specs
    travel = CLASS_RE.search(text)
    if travel:
        specs.append(
            Spec(
                operation=Operation.COUNT_EQ,
                column="Pclass",
                equals=CLASS_EQUALS[travel.group(2).lower()],
                expected=_number(travel.group(1)),
            )
        )
        return specs
    mean = MEAN_RE.search(text)
    if mean:
        specs.append(
            Spec(operation=Operation.MEAN, column=mean.group(1), expected=_number(mean.group(2)))
        )
        return specs
    rows = ROWS_RE.search(text)
    if rows and not re.search(r"\bof the\b", text, re.I):
        specs.append(Spec(operation=Operation.ROWS, expected=_number(rows.group(1))))
    return specs


def _json_object(text: str) -> dict[str, Any] | None:
    body = text.strip()
    if body.startswith("```"):
        body = body.strip("`")
        body = body.removeprefix("json").strip()
    start = body.find("{")
    end = body.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        raw = json.loads(body[start : end + 1])
    except json.JSONDecodeError:
        return None
    return raw if isinstance(raw, dict) else None


def _from_model(text: str, ask: Ask) -> list[Spec]:
    try:
        raw = ask(f"{COMPILE_PROMPT}\n\n{text}")
    except Exception:
        return []
    if not raw or not isinstance(raw, str):
        return []
    payload = _json_object(raw)
    if payload is None:
        return []
    payload.pop("dataset", None)
    payload.pop("dataset_slug", None)
    try:
        return [Spec.model_validate(payload)]
    except ValidationError:
        return []


def compile_claim(text: str, *, ask: Ask | None = None) -> list[Spec]:
    """Return zero or more specs. An empty list means the sentence is not executable."""
    specs = _patterns(text)
    if specs:
        return specs
    caller = ask if ask is not None else repro.ask_model
    return _from_model(text, caller)
