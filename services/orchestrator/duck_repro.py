"""Compile restricted reproduction specs to parameterized DuckDB SQL.

Identifiers are allowlisted. Claim text is never interpolated into SQL.
Pandas ``dsl.execute`` stays the fallback for unsupported ops or a missing
DuckDB install.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from dsl import COUNT_OPS, Operation, Spec, _round, formula, within
from repro_spec import ReproSpec

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SQL_OPS = frozenset({"ROWS", "COUNT", "COUNT_EQ", "SUM", "MEAN", "MEDIAN", "MIN", "MAX"})
BATCH_OPS = frozenset({"ROWS", "MEAN", "SUM", "COUNT"})
_AGG = {
    "SUM": "sum",
    "MEAN": "avg",
    "MEDIAN": "median",
    "MIN": "min",
    "MAX": "max",
}


def available() -> bool:
    try:
        import duckdb  # noqa: F401
    except ImportError:
        return False
    return True


def _quote_ident(name: str) -> str:
    if not IDENTIFIER_RE.fullmatch(name):
        raise ValueError(f"column {name!r} is not an allowed identifier")
    return f'"{name}"'


def _as_spec(spec: Spec | ReproSpec) -> Spec:
    if isinstance(spec, Spec):
        return spec
    equals = spec.arguments.get("equals")
    if equals is None:
        equals = spec.arguments.get("value")
    tolerance = spec.comparison.tolerance if spec.comparison.type == "TOLERANCE" else None
    kwargs: dict[str, Any] = {
        "operation": spec.operation,
        "column": spec.column,
        "expected": spec.expected,
        "tolerance": tolerance,
    }
    if spec.operation == "COUNT_EQ":
        kwargs["equals"] = equals
    return Spec(**kwargs)


def compile_sql(spec: Spec | ReproSpec) -> tuple[str, list[Any]]:
    """Return ``(sql, params)`` for one spec. One SELECT. No claim text in SQL."""
    dsl_spec = _as_spec(spec)
    op = dsl_spec.operation.value
    if op not in SQL_OPS:
        raise ValueError(f"unsupported operation: {op}")
    if op == "ROWS":
        return "SELECT COUNT(*) FROM t", []
    column = dsl_spec.column
    if not column:
        raise ValueError("column is required")
    ident = _quote_ident(column)
    if op == "COUNT_EQ":
        return f"SELECT COUNT(*) FROM t WHERE {ident} = ?", [dsl_spec.equals]
    if op == "COUNT":
        return f"SELECT count({ident}) FROM t", []
    return f"SELECT {_AGG[op]}({ident}) FROM t", []


def _batchable(spec: Spec | ReproSpec) -> bool:
    if isinstance(spec, ReproSpec) and spec.filters:
        return False
    op = spec.operation.value if isinstance(spec.operation, Operation) else str(spec.operation)
    return op in BATCH_OPS


def _alias(dsl_spec: Spec, used: set[str]) -> str:
    op = dsl_spec.operation.value
    if op == "ROWS":
        base = "row_count"
    else:
        column = (dsl_spec.column or "col").lower()
        if not IDENTIFIER_RE.fullmatch(column):
            column = "col"
        base = f"{op.lower()}_{column}"
    alias = base
    suffix = 1
    while alias in used:
        alias = f"{base}_{suffix}"
        suffix += 1
    used.add(alias)
    return alias


def _batch_expr(dsl_spec: Spec) -> str:
    op = dsl_spec.operation.value
    if op == "ROWS":
        return "count(*)"
    ident = _quote_ident(dsl_spec.column or "")
    if op == "COUNT":
        return f"count({ident})"
    if op == "MEAN":
        return f"avg({ident})"
    if op == "SUM":
        return f"sum({ident})"
    raise ValueError(f"not batchable: {op}")


def _batch_items(specs: Sequence[Spec | ReproSpec]) -> list[tuple[int, Spec, str, str]]:
    used: set[str] = set()
    items: list[tuple[int, Spec, str, str]] = []
    for index, spec in enumerate(specs):
        if not _batchable(spec):
            continue
        dsl_spec = _as_spec(spec)
        expr = _batch_expr(dsl_spec)
        items.append((index, dsl_spec, expr, _alias(dsl_spec, used)))
    return items


def compile_batch_sql(specs: Sequence[Spec | ReproSpec]) -> tuple[str, list[Any]]:
    """One SELECT for filter-free ROWS / MEAN / SUM / COUNT. COUNT_EQ is omitted."""
    items = _batch_items(specs)
    if not items:
        raise ValueError("no filter-free ROWS / MEAN / SUM / COUNT specs")
    parts = [f"{expr} AS {alias}" for _, _, expr, alias in items]
    return f"SELECT {', '.join(parts)} FROM t", []


def _blank() -> dict[str, Any]:
    return {
        "actual": None,
        "expected": None,
        "status": "could_not_run",
        "formula": "",
        "steps": [],
        "log": "",
    }


def _pandas_frame(table: Any) -> Any:
    if isinstance(table, (str, Path)):
        import pandas as pd

        return pd.read_csv(table)
    return table


def _bind(con: Any, table: Any) -> None:
    if isinstance(table, (str, Path)):
        con.execute("CREATE TABLE t AS SELECT * FROM read_csv_auto(?)", [str(table)])
        return
    con.register("t", table)


def _columns(con: Any) -> list[str]:
    return [str(row[0]) for row in con.execute("DESCRIBE t").fetchall()]


def _shell(dsl_spec: Spec) -> dict[str, Any]:
    result = _blank()
    result["expected"] = dsl_spec.expected
    result["formula"] = formula(dsl_spec)
    return result


def _fail(dsl_spec: Spec, message: str, steps: list[str] | None = None) -> dict[str, Any]:
    result = _shell(dsl_spec)
    result["log"] = message
    result["steps"] = list(steps) if steps is not None else [message]
    return result


def _early_result(dsl_spec: Spec, table: Any) -> dict[str, Any] | None:
    if table is None:
        return _fail(dsl_spec, "empty table")
    if hasattr(table, "__len__") and not isinstance(table, (str, Path)) and len(table) == 0:
        return _fail(dsl_spec, "empty table")
    if dsl_spec.expected is None:
        expression = formula(dsl_spec)
        return _fail(
            dsl_spec,
            "no expected value on the claim",
            steps=[f"{expression}: no expected value on the claim"],
        )
    return None


def _missing_column(dsl_spec: Spec, names: list[str]) -> dict[str, Any]:
    listed = ", ".join(names)
    message = f"column {dsl_spec.column} not in table (columns: {listed})"
    return _fail(dsl_spec, message)


def _observed_result(dsl_spec: Spec, raw: Any) -> dict[str, Any]:
    result = _shell(dsl_spec)
    if raw is None:
        result["log"] = "empty table"
        result["steps"] = ["empty table"]
        return result
    if dsl_spec.operation.value in COUNT_OPS:
        actual: float | int = int(raw)
    else:
        actual = _round(float(raw))
    result["actual"] = actual
    matched = within(actual, dsl_spec.expected, dsl_spec)
    result["status"] = "reproduced" if matched else "could_not_reproduce"
    expression = result["formula"]
    if dsl_spec.operation == Operation.ROWS:
        result["steps"] = [f"rows = {actual}"]
    else:
        result["steps"] = [f"{expression} = {actual}"]
    if dsl_spec.tolerance is not None:
        band = dsl_spec.tolerance
    elif dsl_spec.operation.value in COUNT_OPS:
        band = 0.5
    else:
        band = max(0.01 * abs(float(dsl_spec.expected)), 1e-9)
    result["steps"].append(
        f"claimed {dsl_spec.expected}, {'within' if matched else 'outside'} tolerance {band}"
    )
    result["log"] = "reproduced" if matched else f"computed {actual}, claimed {dsl_spec.expected}"
    return result


def execute(spec: Spec | ReproSpec, table: Any) -> dict[str, Any]:
    """Run one spec. Shape matches ``dsl.execute``. Falls back to pandas."""
    import dsl

    dsl_spec = _as_spec(spec)
    if dsl_spec.operation.value not in SQL_OPS or not available():
        return dsl.execute(dsl_spec, _pandas_frame(table))

    import duckdb

    early = _early_result(dsl_spec, table)
    if early is not None:
        return early
    try:
        sql, params = compile_sql(dsl_spec)
    except ValueError as error:
        return _fail(dsl_spec, str(error))
    try:
        con = duckdb.connect()
        _bind(con, table)
        names = _columns(con)
        if not names:
            return _fail(dsl_spec, "empty table")
        if dsl_spec.column and dsl_spec.column not in names:
            return _missing_column(dsl_spec, names)
        if con.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 0:
            return _fail(dsl_spec, "empty table")
        raw = con.execute(sql, params).fetchone()[0]
    except Exception as error:
        return _fail(dsl_spec, str(error))
    return _observed_result(dsl_spec, raw)


def execute_batch(specs: Sequence[Spec | ReproSpec], table: Any) -> list[dict[str, Any]]:
    """Run several specs on one table. Compatible aggregations share one SELECT."""
    if not specs:
        return []
    if not available():
        return [execute(spec, table) for spec in specs]

    import duckdb

    results: list[dict[str, Any] | None] = [None] * len(specs)
    dsl_specs = [_as_spec(spec) for spec in specs]
    for index, dsl_spec in enumerate(dsl_specs):
        if dsl_spec.operation.value not in SQL_OPS:
            results[index] = execute(specs[index], table)
            continue
        early = _early_result(dsl_spec, table)
        if early is not None:
            results[index] = early

    pending = [index for index, result in enumerate(results) if result is None]
    if not pending:
        return [item for item in results if item is not None]

    try:
        items = [item for item in _batch_items(specs) if item[0] in pending]
    except ValueError:
        items = []

    if len(items) >= 2:
        try:
            con = duckdb.connect()
            _bind(con, table)
            names = _columns(con)
            if not names or con.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 0:
                for index, dsl_spec, _, _ in items:
                    results[index] = _fail(dsl_spec, "empty table")
            else:
                runnable: list[tuple[int, Spec, str, str]] = []
                for index, dsl_spec, expr, alias in items:
                    if dsl_spec.column and dsl_spec.column not in names:
                        results[index] = _missing_column(dsl_spec, names)
                        continue
                    runnable.append((index, dsl_spec, expr, alias))
                if runnable:
                    sql = f"SELECT {', '.join(f'{expr} AS {alias}' for _, _, expr, alias in runnable)} FROM t"
                    row = con.execute(sql).fetchone()
                    for col, (index, dsl_spec, _, _) in enumerate(runnable):
                        results[index] = _observed_result(dsl_spec, row[col])
        except Exception as error:
            for index, dsl_spec, _, _ in items:
                if results[index] is None:
                    results[index] = _fail(dsl_spec, str(error))

    for index, spec in enumerate(specs):
        if results[index] is None:
            results[index] = execute(spec, table)
    return [item for item in results if item is not None]
