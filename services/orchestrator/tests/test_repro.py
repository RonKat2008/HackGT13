import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

import repro
from paper_audit import audit_paper, load_paper, split_sections

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
HUMAN = FIXTURES / "human.pdf"
DEMO = FIXTURES / "demo_paper.pdf"


@pytest.fixture(autouse=True)
def _no_kaggle_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KAGGLE_USERNAME", raising=False)
    monkeypatch.delenv("KAGGLE_KEY", raising=False)
    monkeypatch.delenv("ARX_KAGGLE_KERNEL", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)


def _sections(text: str) -> dict[str, str]:
    return {
        "abstract": text,
        "introduction": "",
        "methods": "",
        "results": "",
        "references": "",
        "other": "",
    }


def _titanic_csv(directory: Path) -> Path:
    frame = pd.DataFrame(
        {
            "Survived": [1] * 342 + [0] * 549,
            "Pclass": [1] * 216 + [2] * 184 + [3] * 491,
        }
    )
    path = directory / "Titanic-Dataset.csv"
    frame.to_csv(path, index=False)
    return path


def test_claim_without_a_public_dataset_returns_nothing() -> None:
    called = {"n": 0}

    def model(_prompt: str) -> str:
        called["n"] += 1
        return ""

    result = repro.reproduce([], _sections("The accuracy was 0.91 on the benchmark."), model=model)
    assert result == []
    assert called["n"] == 0


def test_missing_table_could_not_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(repro, "DOWNLOADS", tmp_path)
    monkeypatch.setattr(repro, "download_table", lambda *_args: None)
    result = repro.reproduce(
        [],
        _sections(
            "We evaluate on the Titanic passenger dataset (Kaggle, yasserh/titanic-dataset). "
            "Of the 891 passengers, 342 survived."
        ),
        model=lambda _prompt: None,
    )
    assert result
    assert all(item["status"] == "could_not_run" for item in result)
    assert all("dataset not available on this machine" in item["log"] for item in result)
    assert all("code" not in item for item in result)


def test_demo_paper_reproduces_342_and_misses_317(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _titanic_csv(tmp_path)
    monkeypatch.setattr(repro, "DOWNLOADS", tmp_path)
    monkeypatch.setattr(repro, "download_table", lambda *_args: None)
    sections = split_sections(load_paper(DEMO))
    result = repro.reproduce([], sections, model=lambda _prompt: None)
    statuses = [item["status"] for item in result]
    assert statuses.count("reproduced") == 1
    assert statuses.count("could_not_reproduce") == 1
    reproduced = next(item for item in result if item["status"] == "reproduced")
    missed = next(item for item in result if item["status"] == "could_not_reproduce")
    assert reproduced["actual"] == 342
    assert missed["actual"] == 216
    assert missed["expected"] == 317
    assert "Reproduced: 342" in reproduced["steps"]
    assert "Computed 216, claimed 317" in missed["steps"]
    assert "code" not in reproduced


def test_kernel_push_stays_off_unless_asked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _titanic_csv(tmp_path)
    monkeypatch.setattr(repro, "DOWNLOADS", tmp_path)
    monkeypatch.setenv("KAGGLE_USERNAME", "arxaudit")
    monkeypatch.setenv("KAGGLE_KEY", "test-key")
    called = {"n": 0}

    def pusher(_spec: dict) -> dict:
        called["n"] += 1
        return {"status": "match"}

    sections = _sections(
        "We evaluate on the Titanic passenger dataset (Kaggle, yasserh/titanic-dataset). "
        "Of the 891 passengers, 342 survived."
    )
    repro.reproduce([], sections, model=lambda _prompt: None, pusher=pusher)
    assert called["n"] == 0
    monkeypatch.setenv("ARX_KAGGLE_KERNEL", "1")
    repro.reproduce([], sections, model=lambda _prompt: None, pusher=pusher)
    assert called["n"] == 1


def test_notebook_cell_still_compiles(tmp_path: Path) -> None:
    table = tmp_path / "passengers.csv"
    table.write_text("Survived\n1\n0\n1\n", encoding="utf-8")
    spec = {
        "claim_text": "2 of 3",
        "dataset_slug": "demo/passengers",
        "file_name": "",
        "checks": [{"op": "rows", "expected": 3}],
    }
    code = repro.notebook_code(spec, table)
    completed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert completed.returncode == 0
    assert "rows 3" in completed.stdout


def test_kaggle_paper_checks_rows_counts_and_means(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    frame = pd.DataFrame(
        {
            "Survived": [1] * 342 + [0] * 549,
            "Pclass": [1] * 216 + [2] * 184 + [3] * 491,
            "Age": [29.6991] * 891,
            "Fare": [32.2042] * 891,
        }
    )
    path = tmp_path / "Titanic-Dataset.csv"
    frame.to_csv(path, index=False)
    monkeypatch.setattr(repro, "DOWNLOADS", tmp_path)
    monkeypatch.setattr(repro, "download_table", lambda *_args: None)
    sections = split_sections(load_paper(FIXTURES / "kaggle_paper.pdf"))
    result = repro.reproduce([], sections, model=lambda _prompt: (_ for _ in ()).throw(AssertionError("model")))
    by_check = {(item["formula"], item["expected"]): item for item in result}
    assert by_check[("ROWS()", 891)]["status"] == "reproduced"
    assert by_check[("ROWS()", 891)]["actual"] == 891
    assert by_check[("COUNT_EQ(Survived, 1)", 342)]["status"] == "reproduced"
    assert by_check[("COUNT_EQ(Survived, 1)", 342)]["actual"] == 342
    first_true = by_check[("COUNT_EQ(Pclass, 1)", 216)]
    first_false = by_check[("COUNT_EQ(Pclass, 1)", 317)]
    assert first_true["status"] == "reproduced"
    assert first_true["actual"] == 216
    assert first_false["status"] == "could_not_reproduce"
    assert first_false["actual"] == 216
    assert by_check[("MEAN(Age)", 29.7)]["status"] == "reproduced"
    assert by_check[("MEAN(Fare)", 80.0)]["status"] == "could_not_reproduce"
    assert by_check[("MEAN(Fare)", 80.0)]["actual"] == 32.2042
    assert all(item["dataset_slug"] == "yasserh/titanic-dataset" for item in result)
    assert all("code" not in item for item in result)


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
        }

    result = audit_paper(HUMAN, "job-repro", recorder=recorder, repro=worker)
    kinds = {issue["issue_type"] for issue in result["issues"]}
    assert "test" in kinds
    assert ("job-repro", "reproduce", "finished") in calls
