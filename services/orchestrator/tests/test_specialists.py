from uuid import UUID

import pytest

from models import Patch
from specialists import run_specialist


def _query_template_patch(body: str) -> Patch:
    return Patch(
        id=UUID("11111111-1111-4111-8111-111111111111"),
        product="stormcite",
        kind="query_template",
        target="retrieve",
        trigger="not_mentioned",
        body=body,
        patch_text="Search the results section for the metric and the dataset name.",
        status="draft",
        wins=0,
        losses=0,
        fitness_ema=0.0,
        uses=0,
    )


def test_round_1_no_patches_returns_bad_span():
    claims = run_specialist("fixture", "check the metric", 1, [])

    assert len(claims) == 1
    assert claims[0].evidence_span
    assert "BAD" in claims[0].evidence_span
    assert claims[0].source_kind == "fixture"


def test_round_1_query_template_with_metric_returns_good_span():
    patch = _query_template_patch("{metric} results")
    claims = run_specialist("fixture", "check the metric", 1, [patch])

    assert len(claims) == 1
    assert claims[0].evidence_span
    assert "GOOD" in claims[0].evidence_span


def test_round_2_no_patches_returns_good_span():
    claims = run_specialist("fixture", "check the metric", 2, [])

    assert len(claims) == 1
    assert claims[0].evidence_span
    assert "GOOD" in claims[0].evidence_span


def test_unknown_specialist_raises():
    with pytest.raises(KeyError):
        run_specialist("nope", "check the metric", 1, [])
