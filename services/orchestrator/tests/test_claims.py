from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from claims import claim_id, classify, extract_claims, split_sentences
from models import ClaimType, DeskClaim
from paper_audit import audit_paper

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
HALLUCINATED = FIXTURES / "hallucinated.pdf"
HUMAN = FIXTURES / "human.pdf"


def test_split_keeps_decimals_and_et_al() -> None:
    text = (
        "Our model reaches 95.2% accuracy (Vaswani et al., 2017). "
        "This follows later work."
    )
    parts = split_sentences(text)
    assert any("95.2" in part and "et al." in part for part in parts)
    assert any(part.startswith("This follows") for part in parts)
    assert all(len(part) >= 20 for part in parts)


def test_classify_each_type() -> None:
    assert classify("Our model achieves 95.2% accuracy on the held-out benchmark.") == ClaimType.NUMERICAL
    assert (
        classify("Our method improves performance by 7.8 percentage points over the strongest baseline.")
        == ClaimType.NUMERICAL_COMPARISON
    )
    assert classify("Of the 891 passengers, 342 survived.") == ClaimType.DATASET
    assert classify("This result extends the calibration bound of Smith (2099).") == ClaimType.CITATION
    assert (
        classify("The system is robust to distribution shift across all evaluated domains.")
        == ClaimType.SEMANTIC
    )
    assert classify("The router and the reasoning head are optimised jointly.") is None


def test_claim_id_is_stable() -> None:
    first = claim_id("job-a2", "Accuracy reached 95.2% on the public benchmark.")
    second = claim_id("job-a2", "Accuracy reached 95.2% on the public benchmark.")
    assert first == second
    assert len(first) == 12
    assert claim_id("job-other", "Accuracy reached 95.2% on the public benchmark.") != first


def test_hallucinated_audit_has_typed_claims() -> None:
    result = audit_paper(HALLUCINATED, "job-a2")
    claims = result["claims"]
    assert claims
    for item in claims:
        DeskClaim.model_validate(item)
    numerical = next(item for item in claims if item["claim_type"] == "numerical" and "95.2" in item["text"])
    assert numerical["page"] == 1
    citation = next(item for item in claims if item["claim_type"] == "citation" and "Smith" in item["text"])
    assert citation["page"] == 1


def test_human_claims_record_the_checks_that_ran() -> None:
    result = audit_paper(HUMAN, "job-human-a2")
    assert result["claims"]
    for item in result["claims"]:
        DeskClaim.model_validate(item)
    citation = next(item for item in result["claims"] if item["claim_type"] == "citation" and "Lee" in item["text"])
    assert citation["verdict"] == "supported"
    number = next(
        item
        for item in result["claims"]
        if item["claim_type"] == "numerical" and item["section"] == "abstract" and "61.0" in item["text"]
    )
    assert number["verdict"] == "supported"


def test_extract_validates_desk_claim() -> None:
    claims = extract_claims(HALLUCINATED, "job-direct", {"abstract": "", "results": "", "other": ""})
    assert claims
    for item in claims:
        DeskClaim.model_validate(item)


def test_desk_claim_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        DeskClaim.model_validate(
            {
                "claim_id": "abc123def456",
                "text": "Accuracy reached 95.2% on the public benchmark.",
                "claim_type": "numerical",
                "likeness": 0.9,
            }
        )
