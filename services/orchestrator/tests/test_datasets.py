import subprocess

import pytest

import datasets
from dsl import Operation, Spec

TITANIC = (
    "We evaluate on the Titanic passenger dataset (Kaggle, yasserh/titanic-dataset). "
    "Of the 891 passengers, 342 survived."
)
SURVIVED = Spec(operation=Operation.COUNT_EQ, column="Survived", equals=1, expected=342)


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KAGGLE_USERNAME", raising=False)
    monkeypatch.delenv("KAGGLE_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


def test_named_titanic_matches_without_the_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError("kaggle cli")

    monkeypatch.setattr(datasets.subprocess, "run", boom)
    result = datasets.resolve(TITANIC, [SURVIVED])
    assert result["resolution"] == "match"
    assert result["dataset_slug"] == "yasserh/titanic-dataset"
    assert result["steps"] == ["Identified dataset", "Resolved exact dataset"]


def test_two_candidates_stay_ambiguous() -> None:
    def search(_query: str) -> list[dict]:
        return [
            {"slug": "a/housing", "title": "Housing A", "columns": ["MedInc"], "rows": 20640},
            {"slug": "b/housing", "title": "Housing B", "columns": ["MedInc"], "rows": 20640},
        ]

    result = datasets.resolve(
        "The housing corpus holds 20640 districts.",
        [Spec(operation=Operation.ROWS, expected=20640)],
        search=search,
    )
    assert result["resolution"] == "ambiguous"
    assert result["dataset_slug"] == ""
    assert "Exact dataset version could not be verified" in result["steps"]


def test_jev_breaks_a_two_candidate_tie() -> None:
    def search(_query: str) -> list[dict]:
        return [
            {"slug": "a/housing", "title": "Housing A", "columns": ["MedInc"], "rows": 100},
            {"slug": "b/housing", "title": "Housing B", "columns": ["MedInc"], "rows": 100},
        ]

    def judge(_mention: str, title: str) -> str:
        return "match" if title == "Housing B" else "no_match"

    result = datasets.resolve("housing districts", [], search=search, judge=judge)
    assert result["resolution"] == "match"
    assert result["dataset_slug"] == "b/housing"


def test_unknown_mention_is_not_found() -> None:
    result = datasets.resolve("No public table is named.", [SURVIVED], search=lambda _query: [])
    assert result["resolution"] == "not_found"
    assert result["dataset_slug"] == ""
