import os
from pathlib import Path

import fitz

os.environ["ARX_EMBEDDER"] = "hash"

from paper_audit import audit_paper, load_paper, split_sections
from tables import annotate

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
DEMO = FIXTURES / "demo_paper.pdf"


def _table_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Results", fontsize=14, fontname="helv")
    rows = [("Method", "Accuracy"), ("Baseline A", "82.1"), ("Baseline B", "84.7"), ("Ours", "89.2")]
    top = 96
    for label, value in rows:
        bottom = top + 22
        page.draw_rect(fitz.Rect(72, top, 280, bottom), width=0.6)
        page.draw_rect(fitz.Rect(280, top, 420, bottom), width=0.6)
        page.insert_text((78, bottom - 6), label, fontsize=11, fontname="helv")
        page.insert_text((286, bottom - 6), value, fontsize=11, fontname="helv")
        top = bottom
    page.insert_text(
        (72, top + 28),
        "Our method improves performance by 7.8 percentage points over the strongest baseline.",
        fontsize=11,
        fontname="helv",
    )
    doc.save(path)
    doc.close()


def _claim(text: str) -> dict:
    return {
        "claim_id": "cmp",
        "text": text,
        "page": 1,
        "section": "results",
        "claim_type": "numerical_comparison",
        "verdict": "not_checked",
        "confidence": 0.0,
        "depth": "mathematical",
        "rounds": 0,
        "reason": "",
        "evidence": [],
        "steps": [],
        "computation": None,
    }


def test_generated_table_contradicts_7_8(tmp_path: Path) -> None:
    path = tmp_path / "baseline.pdf"
    _table_pdf(path)
    claim = _claim("Our method improves performance by 7.8 percentage points over the strongest baseline.")
    annotate(path, [claim])
    assert claim["verdict"] == "contradicted"
    assert claim["computation"]["spec"]["computed"] == 4.5
    assert claim["computation"]["formula"] == "89.2 − 84.7 = 4.5"
    assert claim["depth"] == "mathematical"


def test_demo_paper_7_8_claim_computes_4_5() -> None:
    result = audit_paper(DEMO, "job-a7")
    claim = next(
        item
        for item in result["claims"]
        if item["claim_type"] == "numerical_comparison" and "7.8" in item["text"]
    )
    assert claim["verdict"] == "contradicted"
    assert claim["computation"]["spec"]["computed"] == 4.5
    assert claim["computation"]["formula"] == "89.2 − 84.7 = 4.5"


def test_abstract_number_check_cites_both_pages() -> None:
    hallucinated = FIXTURES / "hallucinated.pdf"
    result = audit_paper(hallucinated, "job-a7-pages")
    claim = next(
        item
        for item in result["claims"]
        if item["claim_type"] == "numerical" and item["section"] == "abstract" and "95.2" in item["text"]
    )
    pages = {(item.get("section"), item.get("page")) for item in claim["evidence"]}
    assert any(section == "abstract" and isinstance(page, int) for section, page in pages)
    assert any(section == "results" and isinstance(page, int) for section, page in pages)
    assert "95.2" in load_paper(hallucinated)
    assert "results" in split_sections(load_paper(hallucinated))
