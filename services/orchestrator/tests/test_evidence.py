import os
from pathlib import Path

os.environ["ARX_EMBEDDER"] = "hash"

from claims import extract_claims
from evidence import PaperIndex, conflicts
from paper_audit import load_paper, split_sections

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
HALLUCINATED = FIXTURES / "hallucinated.pdf"


def test_neighbors_join_the_evidence_lya_sees_first() -> None:
    from evidence import merge_neighbors

    claim = {
        "text": "Training converges in fewer steps than the baseline because the router is trained jointly.",
        "page": 3,
        "section": "results",
        "evidence": [{"text": "The baselines use the same head without the router.", "section": "results"}],
        "_neighbors": [
            {"page": 3, "section": "results", "text": "Convergence is reached at step 12k for our system and 19k for the baseline."},
            {"page": 3, "section": "results", "text": "The baselines use the same head without the router."},
        ],
    }
    merge_neighbors(claim)
    texts = [item["text"] for item in claim["evidence"]]
    assert "Convergence is reached at step 12k for our system and 19k for the baseline." in texts
    assert texts.count("The baselines use the same head without the router.") == 1
    assert claim["text"] not in texts


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
