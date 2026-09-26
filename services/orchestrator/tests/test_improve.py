from copy import deepcopy
from uuid import uuid4

from app import _live_fixture_patch, _score_run
from fitness import record_result, score
from loop import run_loop
from models import FinalStatus, Patch, PatchKind, PatchStatus, Product
from playbook import top_patches
from specialists import run_specialist
from store import connect, save_patch

GOAL = "check the metric"

VALID_DRAFT = {
    "id": "11111111-1111-4111-8111-111111111111",
    "product": "stormcite",
    "kind": "query_template",
    "target": "fixture",
    "trigger": "not_mentioned",
    "body": "{metric} results",
    "patch_text": "Search the results section for the metric.",
    "status": "draft",
    "wins": 0,
    "losses": 0,
    "fitness_ema": 0.0,
    "uses": 0,
}


def _draft_query_template(**overrides) -> Patch:
    payload = deepcopy(VALID_DRAFT)
    payload.update(overrides)
    if "id" not in overrides:
        payload["id"] = str(uuid4())
    return Patch.model_validate(payload)


def _live_metric_templates(patches: list[Patch]) -> list[Patch]:
    return [
        patch
        for patch in patches
        if patch.status == PatchStatus.LIVE
        and patch.kind == PatchKind.QUERY_TEMPLATE
        and "{metric}" in patch.body
    ]


def test_second_fixture_run_finishes_round_1_with_one_live_query_template(tmp_path):
    conn = connect(tmp_path / "playbook.sqlite")
    try:
        first = run_loop(GOAL)

        assert first.round == 2
        assert first.final_status == FinalStatus.PASSED

        first_fitness = _score_run(first, retry_guard_failed=False)
        promoted = _live_fixture_patch(Product.STORMCITE, first_fitness)
        save_patch(conn, promoted)

        live = top_patches(conn, str(Product.STORMCITE))
        live_templates = _live_metric_templates(live)
        assert len(live_templates) == 1, "expected exactly one live query_template"

        def injected(goal: str, round_num: int, patches: list[Patch]) -> list:
            return run_specialist("fixture", goal, round_num, live + patches)

        second = run_loop(GOAL, specialist=injected)
        second_fitness = _score_run(second, retry_guard_failed=False)

        assert second.round == 1, "second run must finish in round 1 with the live template"
        assert second.final_status == FinalStatus.PASSED
        assert second_fitness >= first_fitness
        assert second.budget.rounds == 1
        assert "GOOD" in second.claims[0].evidence_span
    finally:
        conn.close()


def test_retry_guard_failed_patch_does_not_stay_live(tmp_path):
    conn = connect(tmp_path / "playbook.sqlite")
    try:
        draft = _draft_query_template()
        hack_fitness = score(
            n_claims=1,
            n_supported_or_contradicted=0,
            final_status="unresolved",
            rounds=3,
            retry_guard_failed=True,
        )
        assert hack_fitness < 0

        after_one = record_result(draft, hack_fitness, None)
        assert after_one.status != PatchStatus.LIVE
        assert hack_fitness <= 0

        save_patch(conn, after_one)
        after_one_live = top_patches(conn, str(Product.STORMCITE))
        assert all(patch.id != after_one.id for patch in after_one_live)
        assert _live_metric_templates(after_one_live) == []

        archived = draft
        for _ in range(3):
            archived = record_result(archived, hack_fitness, 0.0)
        assert archived.status == PatchStatus.ARCHIVED
        assert archived.losses == 3
        assert archived.uses == 3

        save_patch(conn, archived)
        remaining = top_patches(conn, str(Product.STORMCITE))
        assert remaining == [] or all(patch.id != archived.id for patch in remaining)
        assert archived.id not in {patch.id for patch in remaining}
    finally:
        conn.close()
