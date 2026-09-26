import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from models import Patch, Run

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "packages" / "schema"

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
        },
        {
            "claim_id": "final",
            "label": "supported",
            "confidence": 0.91,
            "probs": {"supported": 0.91, "contradicted": 0.05, "not_mentioned": 0.04},
        },
    ],
    "playbook_loaded": [VALID_PATCH],
    "playbook_patches": [VALID_PATCH],
    "budget": {"jev_calls": 2, "rounds": 1},
}


def test_loads_valid_run_and_patch():
    patch = Patch.model_validate(VALID_PATCH)
    run = Run.model_validate(VALID_RUN)

    assert patch.kind == "query_template"
    assert patch.status == "draft"
    assert run.product == "landfall"
    assert run.replay_of is None
    assert run.round == 1
    assert run.claims[0].evidence_span
    assert run.jev[1].claim_id == "final"
    assert run.playbook_loaded[0].id == patch.id
    assert run.budget.jev_calls == 2


def test_rejects_claim_missing_evidence_span():
    payload = copy.deepcopy(VALID_RUN)
    del payload["claims"][0]["evidence_span"]

    with pytest.raises(ValidationError):
        Run.model_validate(payload)


def test_rejects_empty_evidence_span():
    payload = copy.deepcopy(VALID_RUN)
    payload["claims"][0]["evidence_span"] = ""

    with pytest.raises(ValidationError):
        Run.model_validate(payload)


def test_rejects_unknown_patch_kind():
    payload = {**VALID_PATCH, "kind": "rewrite_claim"}

    with pytest.raises(ValidationError):
        Patch.model_validate(payload)


def test_accepts_open_source_kind_paper_and_x_post():
    for source_kind in ("paper", "x_post"):
        payload = copy.deepcopy(VALID_RUN)
        payload["claims"][0]["source_kind"] = source_kind
        run = Run.model_validate(payload)
        assert run.claims[0].source_kind == source_kind


def test_rejects_empty_source_kind():
    payload = copy.deepcopy(VALID_RUN)
    payload["claims"][0]["source_kind"] = ""

    with pytest.raises(ValidationError):
        Run.model_validate(payload)


def test_json_schemas_are_draft_2020_12():
    run_schema = json.loads((SCHEMA_DIR / "run.json").read_text())
    patch_schema = json.loads((SCHEMA_DIR / "patch.json").read_text())

    assert run_schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert patch_schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"

    source_kind = run_schema["$defs"]["claim"]["properties"]["source_kind"]
    assert source_kind["type"] == "string"
    assert source_kind.get("minLength", 0) >= 1
    assert "enum" not in source_kind
    assert set(patch_schema["properties"]["kind"]["enum"]) == {
        "query_template",
        "prompt_rule",
        "span_window",
        "retry_guard_block",
    }


def test_accepts_arxaudit_product():
    payload = copy.deepcopy(VALID_RUN)
    payload["product"] = "arxaudit"

    run = Run.model_validate(payload)

    assert run.product == "arxaudit"


def test_batch_schema_freezes_arxaudit_contract():
    batch_schema = json.loads((SCHEMA_DIR / "batch.json").read_text())

    assert batch_schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert set(batch_schema["properties"]["kind"]["enum"]) == {"links", "batch"}

    issue_type = batch_schema["$defs"]["issue_reason"]["properties"]["issue_type"]
    assert set(issue_type["enum"]) == {
        "citation",
        "number",
        "dataset",
        "test",
        "support",
    }

    paper_job_props = batch_schema["$defs"]["paper_job"]["properties"]
    assert "author_email" in paper_job_props
    assert "contacted_at" in paper_job_props
