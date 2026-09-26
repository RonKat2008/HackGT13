from __future__ import annotations

from enum import StrEnum
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, model_validator

COUNT_OPS = frozenset({"ROWS", "COUNT", "COUNT_EQ"})


class Operation(StrEnum):
    ROWS = "ROWS"
    COUNT = "COUNT"
    COUNT_EQ = "COUNT_EQ"
    SUM = "SUM"
    MEAN = "MEAN"
    MEDIAN = "MEDIAN"
    MIN = "MIN"
    MAX = "MAX"
    PERCENT = "PERCENT"
    DIFFERENCE = "DIFFERENCE"
    PERCENT_CHANGE = "PERCENT_CHANGE"


class Spec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Operation
    column: str | None = None
    equals: str | int | float | None = None
    numerator_equals: str | int | float | None = None
    other_column: str | None = None
    expected: float | int | None = None
    tolerance: float | None = None

    @model_validator(mode="after")
    def _require_fields(self) -> Spec:
        op = self.operation
        if op == Operation.COUNT_EQ:
            if not self.column or self.equals is None:
                raise ValueError("COUNT_EQ requires column and equals")
        elif op == Operation.PERCENT:
            if not self.column or self.numerator_equals is None:
                raise ValueError("PERCENT requires column and numerator_equals")
        elif op in {
            Operation.SUM,
            Operation.MEAN,
            Operation.MEDIAN,
            Operation.MIN,
            Operation.MAX,
            Operation.COUNT,
        }:
            if not self.column:
                raise ValueError(f"{op} requires column")
        elif op in {Operation.DIFFERENCE, Operation.PERCENT_CHANGE}:
            if not self.column or not self.other_column:
                raise ValueError(f"{op} requires column and other_column")
        return self


def formula(spec: Spec) -> str:
    op = spec.operation
    if op == Operation.ROWS:
        return "ROWS()"
    if op == Operation.COUNT_EQ:
        return f"COUNT_EQ({spec.column}, {spec.equals})"
    if op == Operation.PERCENT:
        return f"PERCENT({spec.column} == {spec.numerator_equals})"
    if op in {Operation.DIFFERENCE, Operation.PERCENT_CHANGE}:
        return f"{op}({spec.column}, {spec.other_column})"
    return f"{op}({spec.column})"


def _round(value: float | int) -> float | int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return round(float(value), 4)


def _mask(series: pd.Series, value: str | int | float) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        try:
            return series == float(value)
        except (TypeError, ValueError):
            return series.astype(str).str.strip().str.lower() == str(value).strip().lower()
    return series.astype(str).str.strip().str.lower() == str(value).strip().lower()


def _column(frame: pd.DataFrame, name: str | None) -> pd.Series | str:
    if not name:
        return "column is required"
    if name not in frame.columns:
        columns = ", ".join(str(item) for item in frame.columns)
        return f"column {name} not in table (columns: {columns})"
    return frame[name]


def within(actual: float | int, expected: float | int, spec: Spec) -> bool:
    if spec.tolerance is not None:
        return abs(float(actual) - float(expected)) <= spec.tolerance
    if spec.operation.value in COUNT_OPS:
        return abs(float(actual) - float(expected)) <= 0.5
    return abs(float(actual) - float(expected)) <= max(0.01 * abs(float(expected)), 1e-9)


def _run(spec: Spec, frame: pd.DataFrame) -> float | int:
    op = spec.operation
    if op == Operation.ROWS:
        return int(len(frame))
    series = _column(frame, spec.column)
    if isinstance(series, str):
        raise ValueError(series)
    if op == Operation.COUNT:
        return int(series.notna().sum())
    if op == Operation.COUNT_EQ:
        return int(_mask(series, spec.equals).sum())
    if op == Operation.SUM:
        return _round(float(series.sum()))
    if op == Operation.MEAN:
        return _round(float(series.mean()))
    if op == Operation.MEDIAN:
        return _round(float(series.median()))
    if op == Operation.MIN:
        return _round(float(series.min()))
    if op == Operation.MAX:
        return _round(float(series.max()))
    if op == Operation.PERCENT:
        return _round(100.0 * float(_mask(series, spec.numerator_equals).sum()) / max(len(frame), 1))
    other = _column(frame, spec.other_column)
    if isinstance(other, str):
        raise ValueError(other)
    left = float(series.mean())
    right = float(other.mean())
    if op == Operation.DIFFERENCE:
        return _round(left - right)
    if right == 0:
        raise ValueError("PERCENT_CHANGE denominator is 0")
    return _round((left - right) / right * 100)


def execute(spec: Spec, frame: pd.DataFrame) -> dict[str, Any]:
    expression = formula(spec)
    result: dict[str, Any] = {
        "actual": None,
        "expected": spec.expected,
        "status": "could_not_run",
        "formula": expression,
        "steps": [],
        "log": "",
    }
    if frame is None or len(frame) == 0:
        result["log"] = "empty table"
        result["steps"] = ["empty table"]
        return result
    if spec.expected is None:
        result["log"] = "no expected value on the claim"
        result["steps"] = [f"{expression}: no expected value on the claim"]
        return result
    try:
        actual = _run(spec, frame)
    except ValueError as error:
        result["log"] = str(error)
        result["steps"] = [str(error)]
        return result
    result["actual"] = actual
    matched = within(actual, spec.expected, spec)
    result["status"] = "reproduced" if matched else "could_not_reproduce"
    if spec.operation == Operation.ROWS:
        result["steps"] = [f"rows = {actual}"]
    else:
        result["steps"] = [f"{expression} = {actual}"]
    if spec.tolerance is not None:
        band = spec.tolerance
    elif spec.operation.value in COUNT_OPS:
        band = 0.5
    else:
        band = max(0.01 * abs(float(spec.expected)), 1e-9)
    result["steps"].append(f"claimed {spec.expected}, {'within' if matched else 'outside'} tolerance {band}")
    result["log"] = "reproduced" if matched else f"computed {actual}, claimed {spec.expected}"
    return result
