from copy import deepcopy
from uuid import uuid4

from models import Patch, PatchStatus
from fitness import record_result, score

VALID_PATCH = {
    "id": "11111111-1111-4111-8111-111111111111",
    "product": "stormcite",
    "kind": "query_template",
    "target": "retrieve",
    "trigger": "not_mentioned",
    "body": "{metric} {dataset} results section",
    "patch_text": "Search the results section for the metric and the dataset name.",
    "status": "draft",
    "wins": 0,
    "losses": 0,
    "fitness_ema": 0.0,
    "uses": 0,
}


def _patch(**overrides) -> Patch:
    payload = deepcopy(VALID_PATCH)
    payload.update(overrides)
    if "id" not in overrides:
        payload["id"] = str(uuid4())
    return Patch.model_validate(payload)


def test_score_perfect_run_is_one():
    result = score(
        n_claims=3,
        n_supported_or_contradicted=3,
        final_status="passed",
        rounds=1,
        retry_guard_failed=False,
    )

    assert result == 1.0


def test_score_unresolved_hack_is_negative():
    result = score(
        n_claims=1,
        n_supported_or_contradicted=0,
        final_status="unresolved",
        rounds=3,
        retry_guard_failed=True,
    )

    assert result == -0.6
    assert result < 0


def test_record_result_first_positive_fitness_promotes_to_live():
    draft = _patch(status="draft")

    updated = record_result(draft, fitness=0.8, previous_fitness=None)

    assert updated.status == PatchStatus.LIVE
    assert updated.wins == 1
    assert updated.losses == 0
    assert updated.uses == 1
    assert updated.fitness_ema == 0.7 * 0.0 + 0.3 * 0.8
    assert draft.status == PatchStatus.DRAFT
    assert draft.wins == 0
    assert draft.uses == 0


def test_record_result_non_strict_greater_is_loss_and_draft_stays_draft():
    draft = _patch(status="draft", fitness_ema=0.4)

    updated = record_result(draft, fitness=0.4, previous_fitness=0.4)

    assert updated.status == PatchStatus.DRAFT
    assert updated.wins == 0
    assert updated.losses == 1
    assert updated.uses == 1
    assert updated.fitness_ema == 0.7 * 0.4 + 0.0
    assert draft.status == PatchStatus.DRAFT
    assert draft.losses == 0


def test_record_result_three_losses_zero_wins_archives():
    patch = _patch(status="draft")

    after_one = record_result(patch, fitness=0.1, previous_fitness=0.5)
    after_two = record_result(after_one, fitness=0.1, previous_fitness=0.5)
    after_three = record_result(after_two, fitness=0.1, previous_fitness=0.5)

    assert after_one.status == PatchStatus.DRAFT
    assert after_one.losses == 1
    assert after_one.uses == 1
    assert after_two.status == PatchStatus.DRAFT
    assert after_two.losses == 2
    assert after_two.uses == 2
    assert after_three.status == PatchStatus.ARCHIVED
    assert after_three.wins == 0
    assert after_three.losses == 3
    assert after_three.uses == 3
    assert after_three.fitness_ema == 0.7 * after_two.fitness_ema + 0.0


def test_score_two_rounds_is_half_cheap():
    result = score(
        n_claims=2,
        n_supported_or_contradicted=2,
        final_status="contradicted",
        rounds=2,
        retry_guard_failed=False,
    )

    assert result == 0.5 * 1.0 + 0.3 * 1.0 + 0.2 * 0.5 - 0.6 * 0.0


def test_record_result_win_updates_ema_from_previous():
    live = _patch(status="live", wins=1, uses=1, fitness_ema=0.24)

    updated = record_result(live, fitness=0.9, previous_fitness=0.8)

    assert updated.status == PatchStatus.LIVE
    assert updated.wins == 2
    assert updated.losses == 0
    assert updated.uses == 2
    assert updated.fitness_ema == 0.7 * 0.24 + 0.3 * 0.9


def test_record_result_zero_fitness_on_first_run_is_loss():
    draft = _patch(status="draft")

    updated = record_result(draft, fitness=0.0, previous_fitness=None)

    assert updated.status == PatchStatus.DRAFT
    assert updated.wins == 0
    assert updated.losses == 1
    assert updated.uses == 1
