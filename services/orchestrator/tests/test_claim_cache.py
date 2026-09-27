import os
import time
from pathlib import Path

import httpx
import pytest

os.environ["ARX_EMBEDDER"] = "hash"

import evidence
import jev
from evidence import PaperIndex
from lya import cache_key as lya_cache_key, judge_claim as lya_judge_claim
from paper_audit import load_paper, split_sections

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
HALLUCINATED = FIXTURES / "hallucinated.pdf"
FAKE_OPENROUTER = "test-openrouter-key-not-real"

JEV_SUCCESS = {
    "answers": {
        "verdict": {"choice": "supported"},
        "confidence": {"score": 0.88},
    }
}


def test_retrieval_cache_skips_second_scoring(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "runs.sqlite"))
    monkeypatch.setenv("ARX_EMBEDDER", "hash")
    sections = split_sections(load_paper(HALLUCINATED))
    index = PaperIndex(HALLUCINATED, sections)
    claim = "Accuracy reached 95.2% on the public benchmark."

    calls: list[list[str]] = []
    real_embed = evidence._embed_many

    def wrapped_embed(texts: list[str]):
        calls.append([str(item) for item in texts])
        return real_embed(texts)

    monkeypatch.setattr(evidence, "_embed_many", wrapped_embed)

    first = index.retrieve(claim, k=5)
    second = index.retrieve(claim, k=5)

    assert first
    assert second == first
    assert len(calls) == 1
    assert calls[0] == [claim]


def test_lya_local_cache_key_tracks_adapter_mtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "lya.sqlite"))
    adapter_root = tmp_path / "weights"
    adapter_root.mkdir()
    adapter_file = adapter_root / "adapters.safetensors"
    adapter_file.write_bytes(b"version-one")
    model = f"local:{adapter_root}"
    rows = [{"section": "results", "text": "The model accuracy was 61.0%."}]
    claim = "Accuracy reached 61.0% on the public benchmark."

    key_before = lya_cache_key(claim, rows, model)
    time.sleep(0.02)
    adapter_file.write_bytes(b"version-two")
    key_after = lya_cache_key(claim, rows, model)

    assert key_before != key_after

    monkeypatch.setenv("LYA_MODEL", model)
    generate_calls = {"n": 0}

    def fake_generate(_path, _system, _user):
        generate_calls["n"] += 1
        return '{"verdict": "supported", "confidence": 0.95}'

    monkeypatch.setattr("lya_local.generate", fake_generate)

    first = lya_judge_claim(claim, rows)
    adapter_file.write_bytes(b"version-three")
    second = lya_judge_claim(claim, rows)

    assert first["verdict"] == "supported"
    assert second["verdict"] == "supported"
    assert generate_calls["n"] == 2


def test_jev_cache_hits_once_and_errors_are_not_stored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "jev.sqlite"))
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_OPENROUTER)
    claim = "Accuracy reached 95.2% on the public benchmark."
    source = "[p.2] The model accuracy was 61.0%."
    attempts = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(500, text="upstream error")
        return httpx.Response(200, json=JEV_SUCCESS)

    transport = httpx.MockTransport(handler)

    failed = jev.judge_claim(claim, source, transport=transport, api_key=FAKE_OPENROUTER)
    retry = jev.judge_claim(claim, source, transport=transport, api_key=FAKE_OPENROUTER)
    cached = jev.judge_claim(claim, source, transport=transport, api_key=FAKE_OPENROUTER)

    assert failed["not_run"] is True
    assert retry["not_run"] is False
    assert retry["label"] == "supported"
    assert cached == retry
    assert attempts["n"] == 2
