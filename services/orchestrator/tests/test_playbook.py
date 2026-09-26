from copy import deepcopy
from uuid import uuid4

import pytest

from models import Patch
from playbook import accept_patch, apply, top_patches

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


def test_apply_query_template_on_retrieve():
    patch = _patch(
        kind="query_template",
        target="retrieve",
        body="{metric} results",
        status="draft",
    )

    query, extra = apply([patch], "retrieve")

    assert "{metric} results" in query
    assert extra == []


def test_apply_ignores_query_template_for_other_specialist():
    patch = _patch(
        kind="query_template",
        target="extract",
        body="{metric} results",
        status="live",
    )

    query, extra = apply([patch], "retrieve")

    assert query == ""
    assert extra == []


def test_apply_prompt_rule_truncates_to_200():
    body = "x" * 250
    patch = _patch(
        kind="prompt_rule",
        target="extract",
        body=body,
        status="live",
    )

    query, extra = apply([patch], "extract")

    assert query == ""
    assert len(extra) == 1
    assert len(extra[0]) == 200
    assert extra[0] == body[:200]


def test_apply_joins_query_templates_with_space():
    first = _patch(body="{metric} results", status="live")
    second = _patch(body="{dataset} table", status="draft")

    query, extra = apply([first, second], "retrieve")

    assert query == "{metric} results {dataset} table"
    assert extra == []


def test_apply_skips_query_template_without_brace():
    patch = _patch(body="no token here", status="live")

    query, extra = apply([patch], "retrieve")

    assert query == ""
    assert extra == []


def test_apply_span_window_neighbors():
    keep = _patch(
        kind="span_window",
        target="support",
        body="neighbors:1",
        status="live",
    )
    also_keep = _patch(
        kind="span_window",
        target="support",
        body="neighbors:2",
        status="draft",
    )
    skip = _patch(
        kind="span_window",
        target="support",
        body="neighbors:3",
        status="live",
    )

    query, extra = apply([keep, also_keep, skip], "support")

    assert query == ""
    assert extra == ["neighbors:1", "neighbors:2"]


def test_apply_ignores_archived_and_other_kinds():
    archived = _patch(body="{metric} results", status="archived")
    blocked = _patch(
        kind="retry_guard_block",
        body="{metric} results",
        status="live",
    )

    query, extra = apply([archived, blocked], "retrieve")

    assert query == ""
    assert extra == []


def test_top_patches_returns_at_most_five_live(tmp_path):
    from store import connect, save_patch

    conn = connect(tmp_path / "playbook.sqlite")
    try:
        for i in range(7):
            save_patch(
                conn,
                _patch(
                    status="live",
                    fitness_ema=float(i),
                    wins=i,
                    body=f"{{metric}} live {i}",
                ),
            )
        save_patch(
            conn,
            _patch(status="draft", fitness_ema=99.0, wins=99, body="{metric} draft"),
        )
        save_patch(
            conn,
            _patch(
                status="archived",
                fitness_ema=98.0,
                wins=98,
                body="{metric} archived",
            ),
        )

        loaded = top_patches(conn, "stormcite")
    finally:
        conn.close()

    assert len(loaded) <= 5
    assert len(loaded) == 5
    assert all(patch.status == "live" for patch in loaded)
    assert [patch.fitness_ema for patch in loaded] == [6.0, 5.0, 4.0, 3.0, 2.0]


def test_accept_patch_rejects_query_template_without_braces():
    patch = _patch(kind="query_template", body="no braces")

    with pytest.raises(ValueError):
        accept_patch(patch)


def test_accept_patch_allows_save_after_success(tmp_path):
    from store import connect, list_live_patches, save_patch

    patch = _patch(
        kind="query_template",
        body="{metric} results",
        status="live",
    )

    accepted = accept_patch(patch)

    assert accepted is patch
    conn = connect(tmp_path / "playbook.sqlite")
    try:
        save_patch(conn, accepted)
        live = list_live_patches(conn, "stormcite")
    finally:
        conn.close()

    assert len(live) == 1
    assert live[0].id == patch.id
    assert live[0].body == "{metric} results"
