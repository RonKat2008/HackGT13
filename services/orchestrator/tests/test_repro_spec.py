from __future__ import annotations

import pytest
from pydantic import ValidationError

from dsl import Operation, Spec
from repro_spec import ReproSpec, from_spec

FROZEN_FIELDS = {
    "claim_id",
    "dataset_id",
    "file_id",
    "operation",
    "column",
    "filters",
    "arguments",
    "expected",
    "comparison",
    "sentence",
}


def test_field_names_are_frozen() -> None:
    assert set(ReproSpec.model_fields) == FROZEN_FIELDS
    assert set(ReproSpec.model_fields["comparison"].annotation.model_fields) == {
        "type",
        "tolerance",
    }


def test_count_eq_titanic_survived() -> None:
    spec = Spec(operation=Operation.COUNT_EQ, column="Survived", equals=1, expected=342)
    repro = from_spec(spec, "claim-survived", "yasserh/titanic-dataset")
    assert repro.claim_id == "claim-survived"
    assert repro.dataset_id == "yasserh/titanic-dataset"
    assert repro.file_id == ""
    assert repro.operation == "COUNT_EQ"
    assert repro.column == "Survived"
    assert repro.filters == []
    assert repro.arguments["equals"] == 1
    assert repro.arguments["value"] == 1
    assert repro.expected == 342
    assert repro.comparison.type == "EXACT"
    assert repro.comparison.tolerance is None
    assert repro.sentence == ""
    assert set(repro.model_dump()) == FROZEN_FIELDS


def test_mean_age_tolerance() -> None:
    spec = Spec(operation=Operation.MEAN, column="Age", expected=29.7, tolerance=0.1)
    repro = from_spec(spec, "claim-age", "yasserh/titanic-dataset", sentence="The mean Age of 29.7 is reported.")
    assert repro.claim_id == "claim-age"
    assert repro.dataset_id == "yasserh/titanic-dataset"
    assert repro.operation == "MEAN"
    assert repro.column == "Age"
    assert repro.filters == []
    assert repro.arguments == {}
    assert repro.expected == 29.7
    assert repro.comparison.type == "TOLERANCE"
    assert repro.comparison.tolerance == 0.1
    assert repro.sentence == "The mean Age of 29.7 is reported."
    assert set(repro.model_dump()) == FROZEN_FIELDS


def test_unknown_operation_rejected() -> None:
    with pytest.raises(ValueError, match="unknown operation"):
        ReproSpec(
            claim_id="c1",
            dataset_id="yasserh/titanic-dataset",
            operation="CORRELATION",
            expected=1,
            comparison={"type": "EXACT", "tolerance": None},
        )
    spec = Spec.model_construct(operation="CORRELATION", expected=1)
    with pytest.raises(ValueError, match="unknown operation"):
        from_spec(spec, "c1", "yasserh/titanic-dataset")


def test_count_eq_missing_value_rejected() -> None:
    with pytest.raises(ValueError, match="COUNT_EQ requires a value"):
        ReproSpec(
            claim_id="c1",
            dataset_id="yasserh/titanic-dataset",
            operation="COUNT_EQ",
            column="Survived",
            arguments={},
            expected=342,
            comparison={"type": "EXACT", "tolerance": None},
        )
    spec = Spec.model_construct(operation=Operation.COUNT_EQ, column="Survived", equals=None, expected=342)
    with pytest.raises(ValueError, match="COUNT_EQ requires a value"):
        from_spec(spec, "c1", "yasserh/titanic-dataset")
    with pytest.raises(ValidationError):
        Spec(operation=Operation.COUNT_EQ, column="Survived", expected=342)
