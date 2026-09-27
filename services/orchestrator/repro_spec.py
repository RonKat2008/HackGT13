from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dsl import Operation, Spec

ALLOWED_OPERATIONS = frozenset(item.value for item in Operation)


class Comparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["EXACT", "TOLERANCE"]
    tolerance: float | None = None


class ReproSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    dataset_id: str
    file_id: str = ""
    operation: str
    column: str | None = None
    filters: list[Any] = Field(default_factory=list)
    arguments: dict[str, Any] = Field(default_factory=dict)
    expected: float | int | None = None
    comparison: Comparison
    sentence: str = ""

    @model_validator(mode="after")
    def _require_fields(self) -> ReproSpec:
        if self.operation not in ALLOWED_OPERATIONS:
            raise ValueError(f"unknown operation: {self.operation}")
        if self.operation == "COUNT_EQ":
            if self.arguments.get("value") is None and self.arguments.get("equals") is None:
                raise ValueError("COUNT_EQ requires a value")
        return self


def from_spec(
    spec: Spec,
    claim_id: str,
    dataset_id: str,
    *,
    file_id: str = "",
    sentence: str = "",
) -> ReproSpec:
    operation = spec.operation.value if isinstance(spec.operation, Operation) else str(spec.operation)
    if operation not in ALLOWED_OPERATIONS:
        raise ValueError(f"unknown operation: {operation}")
    arguments: dict[str, Any] = {}
    if operation == "COUNT_EQ":
        if spec.equals is None:
            raise ValueError("COUNT_EQ requires a value")
        arguments["equals"] = spec.equals
        arguments["value"] = spec.equals
    if spec.tolerance is not None:
        comparison = Comparison(type="TOLERANCE", tolerance=spec.tolerance)
    else:
        comparison = Comparison(type="EXACT", tolerance=None)
    return ReproSpec(
        claim_id=claim_id,
        dataset_id=dataset_id,
        file_id=file_id,
        operation=operation,
        column=spec.column,
        filters=[],
        arguments=arguments,
        expected=spec.expected,
        comparison=comparison,
        sentence=sentence,
    )
