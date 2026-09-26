from copy import deepcopy
from uuid import uuid4

import pytest

from models import Patch, Run
from store import connect, get_run, insert_run, list_live_patches, record_event, save_patch

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

VALID_RUN = {
    "run_id": "22222222-2222-4222-8222-222222222222",
    "product": "landfall",
    "goal": "Check table 2 holdout accuracy against the cited paper.",
    "goal_hash": "9f86d081884c7d659a2feaa0c55ad015",
    "replay_of": None,
    "round": 1,
    "fitness": 0.0,
    "final_status": "unresolved",
    "claims": [
        {
            "id": "c1",
            "text": "Accuracy was 91.2% on the holdout split.",
            "type": "number",
            "evidence_span": "Table 2 reports 91.2% accuracy on the holdout split.",
            "source_id": "src-1",
            "source_kind": "paper",
        }
    ],
    "tests": [
        {
            "name": "numbers",
            "status": "not_run",
            "log_excerpt": "",
            "where": "local",
        }
    ],
    "jev": [
        {
            "claim_id": "c1",
            "label": "not_mentioned",
            "confidence": 0.4,
            "probs": {"supported": 0.1, "contradicted": 0.1, "not_mentioned": 0.8},
        }
    ],
    "playbook_loaded": [],
    "playbook_patches": [],
    "budget": {"jev_calls": 1, "rounds": 1},
}


def _run(**overrides) -> Run:
    payload = deepcopy(VALID_RUN)
    payload.update(overrides)
    return Run.model_validate(payload)


def _patch(**overrides) -> Patch:
    payload = deepcopy(VALID_PATCH)
    payload.update(overrides)
    return Patch.model_validate(payload)


@pytest.fixture
def conn(tmp_path):
    connection = connect(tmp_path / "playbook.sqlite")
    try:
        yield connection
    finally:
        connection.close()


def test_insert_and_get_run_round_trips(conn):
    run = _run()
    insert_run(conn, run)

    loaded = get_run(conn, run.run_id)

    assert loaded == run
    assert loaded is not None
    assert loaded.goal == run.goal
    assert loaded.claims[0].evidence_span == run.claims[0].evidence_span


def test_missing_run_returns_none(conn):
    assert get_run(conn, uuid4()) is None


def test_list_live_patches_filters_and_orders(conn):
    low_ema = _patch(
        id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        status="live",
        fitness_ema=0.5,
        wins=1,
    )
    high_ema_fewer_wins = _patch(
        id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        status="live",
        fitness_ema=0.9,
        wins=0,
    )
    high_ema_more_wins = _patch(
        id="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        status="live",
        fitness_ema=0.9,
        wins=3,
    )
    draft = _patch(
        id="dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        status="draft",
        fitness_ema=1.0,
        wins=9,
    )
    archived = _patch(
        id="eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
        status="archived",
        fitness_ema=1.0,
        wins=9,
    )
    other_product = _patch(
        id="ffffffff-ffff-4fff-8fff-ffffffffffff",
        product="landfall",
        status="live",
        fitness_ema=1.0,
        wins=9,
    )
    for patch in (
        low_ema,
        high_ema_fewer_wins,
        high_ema_more_wins,
        draft,
        archived,
        other_product,
    ):
        save_patch(conn, patch)

    live = list_live_patches(conn, "stormcite")

    assert [patch.id for patch in live] == [
        high_ema_more_wins.id,
        high_ema_fewer_wins.id,
        low_ema.id,
    ]
    assert all(patch.status == "live" for patch in live)
    assert all(patch.product == "stormcite" for patch in live)


def test_record_event_rejects_result_other_than_win_or_loss(conn):
    patch = _patch()
    run = _run()
    save_patch(conn, patch)
    insert_run(conn, run)

    with pytest.raises(ValueError):
        record_event(conn, patch.id, run.run_id, 0.1, "tie")

    with pytest.raises(ValueError):
        record_event(conn, patch.id, run.run_id, 0.1, "WIN")

    with pytest.raises(ValueError):
        record_event(conn, patch.id, run.run_id, 0.1, "")
