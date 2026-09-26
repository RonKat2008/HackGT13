import json
import os

import httpx
import pytest

from jev import judge_claim, jev_calls_left

FAKE_KEY = "test-openrouter-key-not-real"
DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"

SUCCESS_BODY = {
    "answers": {
        "verdict": {"choice": "supported"},
        "confidence": {"score": 0.9},
    }
}


def _transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def test_judge_claim_maps_choice_and_score_on_200():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=SUCCESS_BODY)

    result = judge_claim(
        "AUC was 0.81",
        "Table 2 reports AUC 0.81 on the holdout.",
        transport=_transport(handler),
        api_key=FAKE_KEY,
    )

    assert result == {
        "label": "supported",
        "confidence": 0.9,
        "probs": {},
        "not_run": False,
    }


def test_judge_claim_missing_keys_default_to_not_mentioned():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    result = judge_claim(
        "a claim",
        "a source",
        transport=_transport(handler),
        api_key=FAKE_KEY,
    )

    assert result["label"] == "not_mentioned"
    assert result["confidence"] == 0.0
    assert result["probs"] == {}
    assert result["not_run"] is False


def test_judge_claim_http_500_is_not_run_for_that_claim_only():
    statuses = iter([500, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        status = next(statuses)
        if status == 500:
            return httpx.Response(500, text="upstream error")
        return httpx.Response(200, json=SUCCESS_BODY)

    transport = _transport(handler)
    failed = judge_claim("claim A", "source A", transport=transport, api_key=FAKE_KEY)
    ok = judge_claim("claim B", "source B", transport=transport, api_key=FAKE_KEY)

    assert failed == {
        "label": "not_mentioned",
        "confidence": 0.0,
        "probs": {},
        "not_run": True,
    }
    assert ok["label"] == "supported"
    assert ok["not_run"] is False


def test_judge_claim_request_exception_is_not_run():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    result = judge_claim(
        "claim",
        "source",
        transport=_transport(handler),
        api_key=FAKE_KEY,
    )

    assert result == {
        "label": "not_mentioned",
        "confidence": 0.0,
        "probs": {},
        "not_run": True,
    }


def test_judge_claim_posts_decisions_body_and_bearer_key():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=SUCCESS_BODY)

    judge_claim(
        "the claim text",
        "the source text",
        transport=_transport(handler),
        api_key=FAKE_KEY,
    )

    assert len(captured) == 1
    request = captured[0]
    assert str(request.url) == DECISIONS_URL
    assert request.method == "POST"
    assert request.headers["Authorization"] == f"Bearer {FAKE_KEY}"
    assert request.headers["Content-Type"] == "application/json"
    assert json.loads(request.content) == {
        "model": "typesafe/jev-1.13",
        "state": {"claim": "the claim text", "source_text": "the source text"},
        "questions": {
            "verdict": {
                "type": "choice",
                "instructions": "How does the source relate to the claim?",
                "criteria": {
                    "supported": "Source supports the claim",
                    "contradicted": "Source contradicts the claim",
                    "not_mentioned": "Source does not mention the claim",
                },
            },
            "confidence": {
                "type": "score",
                "instructions": "Confidence in this verification",
                "criteria": [
                    "Low — indirect or partial evidence",
                    "Medium — plausible alignment with gaps",
                    "High — explicit support or contradiction",
                ],
            },
        },
    }


def test_judge_claim_uses_probs_when_present():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "answers": {
                    "verdict": {
                        "choice": "contradicted",
                        "probs": {"contradicted": 0.8, "supported": 0.1},
                    },
                    "confidence": {"score": 0.75},
                }
            },
        )

    result = judge_claim("c", "s", transport=_transport(handler), api_key=FAKE_KEY)

    assert result["label"] == "contradicted"
    assert result["confidence"] == 0.75
    assert result["probs"] == {"contradicted": 0.8, "supported": 0.1}
    assert result["not_run"] is False


def test_jev_calls_left_allows_call_40_but_stops_the_41st():
    assert jev_calls_left(39) is True
    assert jev_calls_left(40) is False
    assert jev_calls_left(0) is True
    assert jev_calls_left(39, cap=40) is True
    assert jev_calls_left(40, cap=40) is False


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("JEV_LIVE") != "1", reason="set JEV_LIVE=1 to call the live Jev API")
def test_live_jev_decisions_api():
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    result = judge_claim(
        "Water boils at 100 C at sea level.",
        "At standard atmospheric pressure, water boils at 100 degrees Celsius.",
        api_key=api_key,
    )
    assert result["label"] in {"supported", "contradicted", "not_mentioned"}
    assert 0.0 <= result["confidence"] <= 1.0
    assert isinstance(result["probs"], dict)
    assert result["not_run"] is False
