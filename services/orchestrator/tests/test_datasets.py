import subprocess
from pathlib import Path

import pytest

import datasets
import repro
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


def test_same_slug_downloads_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "datasets.sqlite"))
    slug = "yasserh/titanic-dataset"
    calls: list[tuple[str, str]] = []

    def fake_download(slug_arg: str, file_name: str) -> Path:
        calls.append((slug_arg, file_name))
        table = tmp_path / "Titanic-Dataset.csv"
        table.write_text("Survived\n1\n0\n", encoding="utf-8")
        return table

    first = datasets.acquire_table(slug, "", find=lambda *_args: None, download=fake_download)
    second = datasets.acquire_table(slug, "", find=lambda *_args: None, download=fake_download)
    assert first is not None and second is not None
    assert first == second
    assert calls == [(slug, "")]


def test_missing_cached_file_redownloads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "datasets.sqlite"))
    slug = "demo/rebuild"
    stale = tmp_path / "gone.csv"
    stale.write_text("x\n1\n", encoding="utf-8")
    datasets.remember_table(slug, stale)
    stale.unlink()
    calls: list[int] = []

    def fake_download(_slug: str, _file_name: str) -> Path:
        calls.append(1)
        replacement = tmp_path / "fresh.csv"
        replacement.write_text("x\n2\n", encoding="utf-8")
        return replacement

    path = datasets.acquire_table(slug, "", find=lambda *_args: None, download=fake_download)
    assert path is not None
    assert path.name == "fresh.csv"
    assert calls == [1]


def test_failed_download_is_not_cached(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "datasets.sqlite"))
    slug = "demo/missing"

    path = datasets.acquire_table(slug, "", find=lambda *_args: None, download=lambda *_args: None)
    assert path is None
    assert datasets.lookup_table(slug) is None


def test_acquire_table_uses_find_before_download(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "datasets.sqlite"))
    slug = "yasserh/titanic-dataset"
    table = tmp_path / "Titanic-Dataset.csv"
    table.write_text("Survived\n1\n", encoding="utf-8")
    monkeypatch.setattr(repro, "DOWNLOADS", tmp_path)

    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("download should not run when find_table succeeds")

    path = datasets.acquire_table(slug, "", find=repro.find_table, download=boom)
    assert path == table
    assert datasets.lookup_table(slug) == table
