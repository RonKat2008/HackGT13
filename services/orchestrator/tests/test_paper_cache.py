"""T1: a second read of the same PDF bytes skips PyMuPDF."""

import hashlib
import json
import os
import sqlite3
from pathlib import Path

os.environ["ARX_EMBEDDER"] = "hash"

import fitz
import pytest

import paper_audit
import paper_cache
from paper_audit import audit_paper

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
HUMAN = FIXTURES / "human.pdf"


def _noop(*_args: object, **_kwargs: object) -> None:
    return None


def _counting_loader():
    calls: list[str] = []
    real = paper_audit.load_paper

    def wrapped(path):
        calls.append(str(path))
        return real(path)

    return calls, wrapped


def _write_pdf(path: Path, text: str) -> Path:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(72, 72, 540, 720), text, fontsize=11, fontname="helv")
    doc.save(path)
    doc.close()
    return path


def test_second_read_of_human_pdf_skips_load_paper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "runs.sqlite"))
    monkeypatch.setenv("ARX_EMBEDDER", "hash")
    calls, wrapped = _counting_loader()
    monkeypatch.setattr(paper_audit, "load_paper", wrapped)

    audit_paper(HUMAN, "job-first", recorder=_noop)
    assert len(calls) == 1
    digest = hashlib.sha256(HUMAN.read_bytes()).hexdigest()
    assert paper_cache.file_hash(HUMAN) == digest
    first = paper_cache.get(digest)
    assert first is not None
    assert "61.0" in first["sections"]["abstract"]

    def forbidden(path: object) -> str:
        raise AssertionError("load_paper must not run on a cache hit")

    monkeypatch.setattr(paper_audit, "load_paper", forbidden)
    audit_paper(HUMAN, "job-second", recorder=_noop)
    second = paper_cache.get(digest)
    assert second is not None
    assert second["text"] == first["text"]
    assert second["sections"]["abstract"] == first["sections"]["abstract"]
    assert "61.0" in second["sections"]["abstract"]
    assert second["page_count"] == first["page_count"]

    conn = sqlite3.connect(tmp_path / "runs.sqlite")
    try:
        rows = conn.execute(
            "SELECT content_hash, sections_json, tables_json, references_json FROM paper_artifacts"
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 1
    assert rows[0][0] == digest
    stored_sections = json.loads(rows[0][1])
    assert "61.0" in stored_sections["abstract"]
    assert isinstance(json.loads(rows[0][2]), list)
    assert isinstance(json.loads(rows[0][3]), list)


def test_changed_pdf_is_a_new_hash_and_a_new_parse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "runs.sqlite"))
    monkeypatch.setenv("ARX_EMBEDDER", "hash")
    calls, wrapped = _counting_loader()
    monkeypatch.setattr(paper_audit, "load_paper", wrapped)

    audit_paper(HUMAN, "job-human", recorder=_noop)
    other = _write_pdf(
        tmp_path / "other.pdf",
        "Abstract\nA different paper reports 12.5 accuracy.\n",
    )
    audit_paper(other, "job-other", recorder=_noop)
    assert len(calls) == 2
    assert Path(calls[0]).resolve() == HUMAN.resolve()
    assert Path(calls[1]).resolve() == other.resolve()
    assert paper_cache.file_hash(HUMAN) != paper_cache.file_hash(other)

    conn = sqlite3.connect(tmp_path / "runs.sqlite")
    try:
        count = conn.execute("SELECT COUNT(*) FROM paper_artifacts").fetchone()[0]
    finally:
        conn.close()
    assert count == 2
