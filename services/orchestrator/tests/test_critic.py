import inspect

import pytest

from models import Claim, Patch, PatchKind, PatchStatus, Product
from roles import critic


def _failed_claim() -> Claim:
    return Claim(
        id="c1",
        text="The metric is 0.81",
        type="number",
        evidence_span="BAD: source does not mention the metric.",
        source_id="src-1",
        source_kind="fixture",
    )


def test_failed_claim_returns_one_draft_query_template():
    claim = _failed_claim()

    patch = critic(claim, "not_mentioned", ["retrieve"])

    assert isinstance(patch, Patch)
    assert patch.kind == PatchKind.QUERY_TEMPLATE
    assert patch.status == PatchStatus.DRAFT
    assert patch.target == "retrieve"
    assert patch.product == Product.STORMCITE
    assert patch.trigger == "not_mentioned"
    assert patch.wins == 0
    assert patch.losses == 0
    assert patch.fitness_ema == 0.0
    assert patch.uses == 0
    assert "{metric}" in patch.body or "{hazard}" in patch.body


def test_critic_does_not_change_claim_text():
    claim = _failed_claim()
    original_text = claim.text

    critic(claim, "not_mentioned", ["retrieve"])

    assert claim.text is original_text
    assert claim.text == "The metric is 0.81"


def test_model_json_without_brace_falls_back_to_template():
    claim = _failed_claim()

    patch = critic(
        claim,
        "not_mentioned",
        ["retrieve"],
        model_json={"body": "no template here", "patch_text": "nope"},
    )

    assert "{" in patch.body
    assert "{metric}" in patch.body or "{hazard}" in patch.body
    assert patch.body == "{metric} results"
    assert patch.patch_text != "nope"


def test_model_json_with_template_is_used_as_is():
    claim = _failed_claim()

    patch = critic(
        claim,
        "not_mentioned",
        ["retrieve"],
        model_json={"body": "{hazard} {place}", "patch_text": "Search the hazard."},
    )

    assert patch.body == "{hazard} {place}"
    assert patch.patch_text == "Search the hazard."


def test_empty_allow_list_raises():
    claim = _failed_claim()

    with pytest.raises(ValueError):
        critic(claim, "not_mentioned", [])


def test_critic_has_no_path_argument():
    assert "path" not in inspect.signature(critic).parameters
