"""DuckDB execute for ROWS / COUNT_EQ / SUM / MEAN / MEDIAN / MIN / MAX.

The CSV uses the same 342/549 Survived and 216/184/491 Pclass pattern as
``test_repro._titanic_csv``.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import duck_repro
import repro
from dsl import Operation, Spec, within
from repro_spec import from_spec


def _titanic_csv(directory: Path) -> Path:
    frame = pd.DataFrame(
        {
            "Survived": [1] * 342 + [0] * 549,
            "Pclass": [1] * 216 + [2] * 184 + [3] * 491,
            "Age": [29.6991] * 891,
        }
    )
    path = directory / "Titanic-Dataset.csv"
    frame.to_csv(path, index=False)
    return path


def test_rows_891_reproduced(tmp_path: Path) -> None:
    result = duck_repro.execute(Spec(operation=Operation.ROWS, expected=891), _titanic_csv(tmp_path))
    assert result["status"] == "reproduced"
    assert result["actual"] == 891
    assert result["expected"] == 891
    assert result["formula"] == "ROWS()"
    assert "rows = 891" in result["steps"]


def test_count_eq_survived_342_reproduced(tmp_path: Path) -> None:
    spec = Spec(operation=Operation.COUNT_EQ, column="Survived", equals=1, expected=342)
    result = duck_repro.execute(spec, _titanic_csv(tmp_path))
    assert result["status"] == "reproduced"
    assert result["actual"] == 342
    assert result["formula"] == "COUNT_EQ(Survived, 1)"


def test_count_eq_pclass_317_is_216(tmp_path: Path) -> None:
    spec = Spec(operation=Operation.COUNT_EQ, column="Pclass", equals=1, expected=317)
    result = duck_repro.execute(spec, _titanic_csv(tmp_path))
    assert result["status"] == "could_not_reproduce"
    assert result["actual"] == 216
    assert result["expected"] == 317
    assert "computed 216, claimed 317" in result["log"]


def test_compile_sql_is_parameterized() -> None:
    sql, params = duck_repro.compile_sql(Spec(operation=Operation.ROWS, expected=891))
    assert sql == "SELECT COUNT(*) FROM t"
    assert params == []

    sql, params = duck_repro.compile_sql(
        Spec(operation=Operation.COUNT_EQ, column="Survived", equals=1, expected=342)
    )
    assert sql == 'SELECT COUNT(*) FROM t WHERE "Survived" = ?'
    assert params == [1]
    assert "342" not in sql

    injected = "1; DROP TABLE t -- of the 891 passengers"
    sql, params = duck_repro.compile_sql(
        Spec(operation=Operation.COUNT_EQ, column="Survived", equals=injected, expected=342)
    )
    assert "?" in sql
    assert injected not in sql
    assert params == [injected]

    for op, fn in (
        (Operation.SUM, "sum"),
        (Operation.MEAN, "avg"),
        (Operation.MEDIAN, "median"),
        (Operation.MIN, "min"),
        (Operation.MAX, "max"),
    ):
        sql, params = duck_repro.compile_sql(Spec(operation=op, column="Age", expected=1))
        assert sql == f'SELECT {fn}("Age") FROM t'
        assert params == []


def test_reject_non_allowlisted_column() -> None:
    with pytest.raises(ValueError, match="not an allowed identifier"):
        duck_repro.compile_sql(
            Spec.model_construct(operation=Operation.MEAN, column="Age; DROP TABLE t", expected=1)
        )


def test_aggregates_match_dsl_rounding() -> None:
    frame = pd.DataFrame({"Age": [10.0, 20.0, 30.0]})
    assert duck_repro.execute(Spec(operation=Operation.SUM, column="Age", expected=60), frame)["actual"] == 60
    assert duck_repro.execute(Spec(operation=Operation.MEAN, column="Age", expected=20), frame)["status"] == "reproduced"
    assert duck_repro.execute(Spec(operation=Operation.MEDIAN, column="Age", expected=20), frame)["status"] == "reproduced"
    assert duck_repro.execute(Spec(operation=Operation.MIN, column="Age", expected=10), frame)["status"] == "reproduced"
    assert duck_repro.execute(Spec(operation=Operation.MAX, column="Age", expected=30), frame)["status"] == "reproduced"


def test_execute_repro_spec(tmp_path: Path) -> None:
    spec = from_spec(
        Spec(operation=Operation.COUNT_EQ, column="Survived", equals=1, expected=342),
        "c1",
        "yasserh/titanic-dataset",
    )
    result = duck_repro.execute(spec, _titanic_csv(tmp_path))
    assert result["status"] == "reproduced"
    assert result["actual"] == 342


def test_context_prefers_duckdb(tmp_path: Path) -> None:
    frame = pd.read_csv(_titanic_csv(tmp_path))
    ctx = repro.ReproductionContext()
    assert ctx._engine == "duckdb"
    result = ctx.execute(Spec(operation=Operation.ROWS, expected=891), frame)
    assert result["status"] == "reproduced"
    assert result["actual"] == 891


def test_batch_rows_and_mean_age_one_select(tmp_path: Path) -> None:
    path = _titanic_csv(tmp_path)
    specs = [
        Spec(operation=Operation.ROWS, expected=891),
        Spec(operation=Operation.MEAN, column="Age", expected=29.7),
    ]
    sql, params = duck_repro.compile_batch_sql(specs)
    lowered = sql.lower()
    assert lowered.count("select") == 1
    assert "count(*)" in lowered
    assert "avg" in lowered
    assert params == []

    results = duck_repro.execute_batch(specs, path)
    assert len(results) == 2
    assert results[0]["actual"] == 891
    assert results[0]["status"] == "reproduced"
    assert results[0]["formula"] == "ROWS()"
    assert within(results[1]["actual"], 29.7, specs[1])
    assert results[1]["status"] == "reproduced"
    assert results[1]["formula"] == "MEAN(Age)"

    singles = [duck_repro.execute(spec, path) for spec in specs]
    for batched, single in zip(results, singles, strict=True):
        assert batched["status"] == single["status"]
        assert batched["formula"] == single["formula"]
        assert batched["log"] == single["log"]
        assert batched["actual"] == single["actual"]


def test_batch_leaves_count_eq_out_of_shared_select(tmp_path: Path) -> None:
    path = _titanic_csv(tmp_path)
    specs = [
        Spec(operation=Operation.ROWS, expected=891),
        Spec(operation=Operation.COUNT_EQ, column="Survived", equals=1, expected=342),
        Spec(operation=Operation.MEAN, column="Age", expected=29.7),
        Spec(operation=Operation.COUNT_EQ, column="Pclass", equals=1, expected=317),
    ]
    sql, _params = duck_repro.compile_batch_sql(specs)
    lowered = sql.lower()
    assert "where" not in lowered
    assert "count(*)" in lowered
    assert "avg" in lowered

    results = duck_repro.execute_batch(specs, path)
    assert results[0]["actual"] == 891
    assert results[1]["actual"] == 342
    assert results[1]["status"] == "reproduced"
    assert results[1]["formula"] == "COUNT_EQ(Survived, 1)"
    assert within(results[2]["actual"], 29.7, specs[2])
    assert results[3]["actual"] == 216
    assert results[3]["status"] == "could_not_reproduce"
    assert "computed 216, claimed 317" in results[3]["log"]
