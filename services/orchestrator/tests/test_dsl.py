from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from dsl import Operation, Spec, execute, formula


def titanic() -> pd.DataFrame:
    survived = np.array([1] * 342 + [0] * 549)
    pclass = np.array([1] * 216 + [2] * 184 + [3] * 491)
    sex = np.array(["male"] * 577 + ["female"] * 314)
    age = np.array([float(i % 70) if i % 11 else np.nan for i in range(891)])
    fare = np.linspace(7.0, 80.0, 891)
    return pd.DataFrame(
        {
            "Survived": survived,
            "Pclass": pclass,
            "Sex": sex,
            "Age": age,
            "Fare": fare,
        }
    )


def test_rows_reproduced() -> None:
    result = execute(Spec(operation=Operation.ROWS, expected=891), titanic())
    assert result["status"] == "reproduced"
    assert result["actual"] == 891
    assert result["formula"] == "ROWS()"
    assert "rows = 891" in result["steps"]


def test_count_eq_survived() -> None:
    spec = Spec(operation=Operation.COUNT_EQ, column="Survived", equals=1, expected=342)
    result = execute(spec, titanic())
    assert result["status"] == "reproduced"
    assert result["actual"] == 342
    assert formula(spec) == "COUNT_EQ(Survived, 1)"


def test_count_eq_pclass_mismatch() -> None:
    result = execute(
        Spec(operation=Operation.COUNT_EQ, column="Pclass", equals=1, expected=317),
        titanic(),
    )
    assert result["status"] == "could_not_reproduce"
    assert result["actual"] == 216


def test_count_eq_sex_is_case_insensitive() -> None:
    result = execute(
        Spec(operation=Operation.COUNT_EQ, column="Sex", equals="MALE", expected=577),
        titanic(),
    )
    assert result["status"] == "reproduced"
    assert result["actual"] == 577


def test_percent_survived() -> None:
    spec = Spec(operation=Operation.PERCENT, column="Survived", numerator_equals=1, expected=38.38)
    result = execute(spec, titanic())
    assert result["status"] == "reproduced"
    assert abs(float(result["actual"]) - 38.3838) < 1e-6
    assert formula(spec) == "PERCENT(Survived == 1)"


def test_mean_missing_column() -> None:
    result = execute(Spec(operation=Operation.MEAN, column="Weight", expected=30), titanic())
    assert result["status"] == "could_not_run"
    assert "column Weight not in table" in result["log"]


def test_count_eq_requires_equals() -> None:
    with pytest.raises(ValidationError):
        Spec(operation=Operation.COUNT_EQ, column="Survived", expected=1)


def test_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        Spec.model_validate({"operation": "ROWS", "expected": 891, "extra": "no"})


def test_difference_and_percent_change() -> None:
    frame = titanic()
    claimed = float(frame["Fare"].mean()) - float(frame["Age"].mean())
    diff = execute(
        Spec(operation=Operation.DIFFERENCE, column="Fare", other_column="Age", expected=round(claimed, 4)),
        frame,
    )
    assert diff["status"] == "reproduced"
    assert diff["formula"] == "DIFFERENCE(Fare, Age)"
    change = execute(
        Spec(operation=Operation.PERCENT_CHANGE, column="Fare", other_column="Age", expected=70),
        frame,
    )
    assert change["status"] in {"reproduced", "could_not_reproduce"}
    assert change["formula"] == "PERCENT_CHANGE(Fare, Age)"


def test_no_expected_cannot_reproduce() -> None:
    result = execute(Spec(operation=Operation.ROWS), titanic())
    assert result["status"] == "could_not_run"
    assert result["log"] == "no expected value on the claim"


def test_empty_frame() -> None:
    result = execute(Spec(operation=Operation.ROWS, expected=0), pd.DataFrame())
    assert result["status"] == "could_not_run"
    assert result["log"] == "empty table"
