from pathlib import Path

import pytest

import datasets
import repro


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KAGGLE_USERNAME", raising=False)
    monkeypatch.delenv("KAGGLE_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("ARX_KAGGLE_KERNEL", raising=False)


def _sections(text: str) -> dict[str, str]:
    return {
        "abstract": text,
        "introduction": "",
        "methods": "",
        "results": "",
        "references": "",
        "other": "",
    }


def _rows_paper() -> str:
    return (
        "We evaluate on the Titanic passenger dataset (Kaggle, yasserh/titanic-dataset). "
        "The table contains 3 passengers."
    )


def test_second_reproduce_does_not_execute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "repro-cache.sqlite"))
    table = tmp_path / "Titanic-Dataset.csv"
    table.write_text("Survived\n1\n0\n1\n", encoding="utf-8")
    monkeypatch.setattr(repro, "DOWNLOADS", tmp_path)
    monkeypatch.setattr(repro, "download_table", lambda *_args: None)

    calls = {"n": 0}
    real = repro.ReproductionContext.execute

    def counting(self: repro.ReproductionContext, spec: object, frame: object) -> dict:
        calls["n"] += 1
        return real(self, spec, frame)

    monkeypatch.setattr(repro.ReproductionContext, "execute", counting)
    sections = _sections(_rows_paper())

    first = repro.reproduce([], sections, model=lambda _prompt: None)
    assert calls["n"] == 1
    assert first
    assert first[0]["status"] == "reproduced"
    assert first[0]["actual"] == 3

    second = repro.reproduce([], sections, model=lambda _prompt: None)
    assert calls["n"] == 1
    assert second[0]["status"] == "reproduced"
    assert second[0]["actual"] == 3


def test_could_not_run_is_not_cached(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "repro-cache.sqlite"))
    table = tmp_path / "Titanic-Dataset.csv"
    table.write_text("Survived\n", encoding="utf-8")
    monkeypatch.setattr(repro, "DOWNLOADS", tmp_path)
    monkeypatch.setattr(repro, "download_table", lambda *_args: None)

    calls = {"n": 0}
    real = repro.ReproductionContext.execute

    def counting(self: repro.ReproductionContext, spec: object, frame: object) -> dict:
        calls["n"] += 1
        return real(self, spec, frame)

    monkeypatch.setattr(repro.ReproductionContext, "execute", counting)
    sections = _sections(_rows_paper())

    first = repro.reproduce([], sections, model=lambda _prompt: None)
    assert first
    assert first[0]["status"] == "could_not_run"
    assert calls["n"] == 1

    second = repro.reproduce([], sections, model=lambda _prompt: None)
    assert second[0]["status"] == "could_not_run"
    assert calls["n"] == 2


def test_remember_skips_could_not_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "repro-cache.sqlite"))
    datasets.remember_repro_result("k1", None, "could_not_run")
    assert datasets.lookup_repro_result("k1") is None
    datasets.remember_repro_result("k1", 3, "reproduced")
    assert datasets.lookup_repro_result("k1") == {"actual": 3, "status": "reproduced"}
