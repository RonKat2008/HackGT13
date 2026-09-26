import json
import subprocess
import sys
from pathlib import Path

import pytest

import repro
from paper_audit import audit_paper

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
HUMAN = FIXTURES / "human.pdf"


@pytest.fixture(autouse=True)
def _no_kaggle_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KAGGLE_USERNAME", raising=False)
    monkeypatch.delenv("KAGGLE_KEY", raising=False)


def _sections(text: str) -> dict[str, str]:
    return {
        "abstract": text,
        "introduction": "",
        "methods": "",
        "results": "",
        "references": "",
        "other": "",
    }


def _table(tmp_path: Path) -> Path:
    path = tmp_path / "passengers.csv"
    path.write_text("Survived\n1\n0\n1\n", encoding="utf-8")
    return path


def test_claim_without_a_public_dataset_is_not_run() -> None:
    called = {"n": 0}

    def model(_prompt: str) -> str:
        called["n"] += 1
        return ""

    result = repro.reproduce([], _sections("The accuracy was 0.91."), model=model)
    assert result["status"] == "not_run"
    assert called["n"] == 0


def test_written_count_matches_the_table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    table = _table(tmp_path)
    monkeypatch.setattr(repro, "find_table", lambda *_args: table)
    monkeypatch.setattr(repro, "download_table", lambda *_args: None)
    sentence = "On demo/passengers, 2 of 3 passengers have Survived equal to 1."
    result = repro.reproduce([], _sections(sentence), model=lambda _prompt: None)
    assert result["where"] == "local"
    assert result["status"] == "match"
    assert "rows 3" in result["log"]
    assert table.name in result["code"]


def test_written_count_mismatch_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    table = _table(tmp_path)
    monkeypatch.setattr(repro, "find_table", lambda *_args: table)
    monkeypatch.setattr(repro, "download_table", lambda *_args: None)
    sentence = "On demo/passengers, 2 of 9 passengers have Survived equal to 1."
    result = repro.reproduce([], _sections(sentence), model=lambda _prompt: None)
    assert result["status"] == "mismatch"
    assert "9" in result["detail"]


def test_model_spec_is_used_when_it_is_a_table_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    table = _table(tmp_path)
    monkeypatch.setattr(repro, "find_table", lambda *_args: table)
    payload = {
        "reproducible": True,
        "claim_text": "The sum of Survived is 2.",
        "dataset_slug": "demo/passengers",
        "file_name": "",
        "checks": [{"op": "sum", "column": "Survived", "expected": 2}],
    }
    result = repro.reproduce(
        [],
        _sections("See demo/passengers."),
        model=lambda _prompt: json.dumps(payload),
    )
    assert result["status"] == "match"
    assert "sum Survived" in result["log"]


def test_kernel_result_wins_when_credentials_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    table = _table(tmp_path)
    monkeypatch.setattr(repro, "find_table", lambda *_args: table)
    monkeypatch.setenv("KAGGLE_USERNAME", "arxaudit")
    monkeypatch.setenv("KAGGLE_KEY", "test-key")
    result = repro.reproduce(
        [],
        _sections("On demo/passengers, 2 of 3 passengers have Survived equal to 1."),
        model=lambda _prompt: None,
        pusher=lambda _spec: {
            "where": "kaggle",
            "status": "match",
            "log": "kernel passed",
            "detail": "The public table matches the count written in the paper.",
            "kernel_url": repro.KERNEL_URL,
        },
    )
    assert result["where"] == "kaggle"
    assert result["log"] == "kernel passed"
    assert result["kernel_url"] == repro.KERNEL_URL
    assert "import csv" in result["code"]


def test_notebook_cell_prints_the_check(tmp_path: Path) -> None:
    table = _table(tmp_path)
    spec = repro.propose(
        [],
        _sections("On demo/passengers, 2 of 3 passengers have Survived equal to 1."),
        model=lambda _prompt: None,
    )
    assert spec is not None
    code = repro.notebook_code(spec, table)
    completed = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert "rows 3" in completed.stdout
    compile(repro._kernel_source(spec), "<kernel>", "exec")


def test_audit_records_a_failed_rerun() -> None:
    calls: list[tuple[str, str, str]] = []

    def recorder(job_id: str, specialist: str, state: str, detail: str) -> None:
        calls.append((job_id, specialist, state))

    def worker(_claims: list, _sections: dict) -> dict:
        return {
            "where": "local",
            "status": "mismatch",
            "log": "rows 2 expected 9",
            "detail": "The table has 2 rows. The paper says 9.",
            "claim_text": "2 of 9 passengers have Survived equal to 1.",
            "kernel_url": None,
            "code": "print('rerun')",
        }

    result = audit_paper(HUMAN, "job-repro", recorder=recorder, repro=worker)
    kinds = {issue["issue_type"] for issue in result["issues"]}
    assert "test" in kinds
    assert ("job-repro", "kaggle_runner", "finished") in calls
