import os
from pathlib import Path

os.environ["ARX_EMBEDDER"] = "hash"

from claims import extract_claims
from evidence import PaperIndex, conflicts
from paper_audit import load_paper, split_sections

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
HALLUCINATED = FIXTURES / "hallucinated.pdf"


def test_number_conflict_requires_a_shared_unit() -> None:
    assert conflicts("Accuracy reached 95.2% on the benchmark.", "The model score was 61.0%.")
    assert not conflicts(
        "Accuracy reached 95.2% on the benchmark.",
        "Accuracy reached 95.2% on the benchmark.",
    )
    assert not conflicts("The room had 12 chairs.", "The room had 4 chairs.")


def test_falsifier_ranks_the_disagreeing_accuracy_first() -> None:
    sections = split_sections(load_paper(HALLUCINATED))
    claim = next(
        item
        for item in extract_claims(HALLUCINATED, "job-a3", sections)
        if "95.2" in item["text"] and item["section"] == "abstract"
    )
    index = PaperIndex(HALLUCINATED, sections)
    hits = index.falsifier(claim)
    assert hits
    assert "61.0" in hits[0]["text"]
    assert hits[0]["section"] != "abstract"
    assert len(index.retrieve(claim["text"], k=5)) <= 5
