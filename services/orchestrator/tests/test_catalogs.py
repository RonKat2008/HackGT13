import os

import httpx

os.environ["ARX_EMBEDDER"] = "hash"

from catalogs import decide, lookup
from references import attach

VASWANI = {
    "raw": "Vaswani 2017 Attention is all you need",
    "year": "2017",
    "doi": "10.48550/arXiv.1706.03762",
    "title": "Attention is all you need",
    "authors": ["Vaswani"],
}
SMITH = {
    "raw": "Smith 2099 Calibration bounds for adaptive reasoning",
    "year": "2099",
    "doi": "",
    "title": "Calibration bounds for adaptive reasoning",
    "authors": ["Smith"],
}


def _claim(text: str) -> dict:
    return {
        "claim_id": "cite",
        "text": text,
        "claim_type": "citation",
        "verdict": "not_checked",
        "confidence": 0.0,
        "reason": "",
        "steps": [],
        "catalog": None,
    }


def _transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def _empty(request: httpx.Request) -> httpx.Response:
    host = request.url.host
    if "crossref" in host:
        return httpx.Response(200, json={"message": {"items": []}})
    if "openalex" in host:
        return httpx.Response(200, json={"results": []})
    return httpx.Response(200, json={"data": []})


def _vaswani(request: httpx.Request) -> httpx.Response:
    host = request.url.host
    if "crossref" in host:
        return httpx.Response(
            200,
            json={
                "message": {
                    "items": [
                        {
                            "title": ["Attention Is All You Need"],
                            "author": [{"family": "Vaswani"}],
                            "issued": {"date-parts": [[2017]]},
                            "DOI": "10.48550/arXiv.1706.03762",
                        }
                    ]
                }
            },
        )
    if "openalex" in host:
        return httpx.Response(200, json={"results": []})
    return httpx.Response(200, json={"data": []})


def _weak(request: httpx.Request) -> httpx.Response:
    host = request.url.host
    if "crossref" in host:
        return httpx.Response(
            200,
            json={
                "message": {
                    "items": [
                        {
                            "title": ["Some other calibration paper"],
                            "author": [{"family": "Smith"}],
                            "issued": {"date-parts": [[2099]]},
                            "DOI": "",
                        }
                    ]
                }
            },
        )
    if "openalex" in host:
        return httpx.Response(200, json={"results": []})
    return httpx.Response(200, json={"data": []})


def _down(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(503, json={"error": "down"})


def test_vaswani_resolves_and_smith_stays_unresolved(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "catalog.sqlite"))
    vaswani = lookup(VASWANI["raw"], VASWANI, transport=_transport(_vaswani))
    verdict, confidence, _reason = decide(_claim("See (Vaswani et al., 2017)."), vaswani)
    assert verdict == "supported"
    assert confidence >= 0.85
    assert any(item["status"] == "match" and item["catalog"] == "crossref" for item in vaswani["queried"])

    smith = lookup(SMITH["raw"], SMITH, transport=_transport(_empty))
    verdict, _confidence, reason = decide(_claim("See (Smith, 2099)."), smith)
    assert verdict == "unresolved"
    assert "catalogs searched" in reason
    assert all(item["status"] == "no_match" for item in smith["queried"])


def test_network_error_is_not_checked_and_a_weak_match_asks_jev(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "catalog.sqlite"))
    failed = lookup(VASWANI["raw"] + " offline", VASWANI, transport=_transport(_down))
    verdict, confidence, _reason = decide(_claim("See (Vaswani et al., 2017)."), failed)
    assert verdict == "not_checked"
    assert verdict != "unresolved"
    assert confidence == 0.0

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key-not-real")
    seen: list[str] = []

    def judge(claim_text, source_text, transport=None, api_key=None):
        seen.append(source_text)
        return {"label": "supported", "confidence": 0.66, "probs": {}, "not_run": False}

    monkeypatch.setattr("jev.judge_claim", judge)
    weak = lookup("Smith weak 2099", SMITH, transport=_transport(_weak))
    verdict, confidence, _reason = decide(_claim("This result extends Smith (2099)."), weak)
    assert verdict == "supported"
    assert confidence == 0.66
    assert seen
    assert "candidate represent the reference" in seen[0]


def test_attach_stores_the_catalog_on_the_claim(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "catalog.sqlite"))
    references = (
        "1. Vaswani, A. (2017). Attention is all you need. doi:10.48550/arXiv.1706.03762\n"
        "3. Smith, J. (2099). Calibration bounds for adaptive reasoning."
    )
    claims = [
        _claim("The design follows (Vaswani et al., 2017)."),
        _claim("The bound is stated for adaptive estimators (Smith, 2099)."),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.query.decode("utf-8", "ignore")
        if "Vaswani" in query or "1706.03762" in query:
            return _vaswani(request)
        return _empty(request)

    attach(claims, references, transport=_transport(handler))
    assert claims[0]["verdict"] == "supported"
    assert claims[1]["verdict"] == "unresolved"
    assert claims[0]["catalog"]["queried"]
    assert any(item["catalog"] == "crossref" for item in claims[0]["catalog"]["queried"])


def test_same_doi_hits_transport_once_for_two_queries(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "catalog.sqlite"))
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host or "")
        return _vaswani(request)

    transport = _transport(handler)
    query_a = "Vaswani et al. 2017 Attention is all you need NeurIPS"
    query_b = "See Vaswani, A., et al. (2017). Attention is all you need."
    first = lookup(query_a, VASWANI, transport=transport)
    second = lookup(query_b, VASWANI, transport=transport)
    verdict_a, confidence_a, _ = decide(_claim("A"), first)
    verdict_b, confidence_b, _ = decide(_claim("B"), second)
    assert verdict_a == "supported" and verdict_b == "supported"
    assert confidence_a >= 0.85 and confidence_b >= 0.85
    assert len(calls) == 3


def test_attach_same_doi_does_not_repeat_catalog_http(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "catalog.sqlite"))
    references = (
        "1. Vaswani, A. (2017). Attention is all you need. doi:10.48550/arXiv.1706.03762\n"
        "2. Vaswani, A. (2017). Attention is all you need. doi:10.48550/arXiv.1706.03762"
    )
    claims = [
        _claim("First mention (Vaswani et al., 2017)."),
        _claim("Second mention (Vaswani et al., 2017)."),
    ]
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host or "")
        return _vaswani(request)

    attach(claims, references, transport=_transport(handler))
    assert claims[0]["verdict"] == "supported"
    assert claims[1]["verdict"] == "supported"
    assert len(calls) == 3


def test_catalog_error_retries_once_then_skips_http(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "catalog.sqlite"))
    import catalogs as catalogs_mod

    catalogs_mod._error_retried.clear()
    calls: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503, json={"error": "down"})

    transport = _transport(handler)
    query = VASWANI["raw"] + " retry-once"
    first = lookup(query, VASWANI, transport=transport)
    second = lookup(query + " again", VASWANI, transport=transport)
    third = lookup(query + " third", VASWANI, transport=transport)
    for catalog in (first, second, third):
        verdict, confidence, _ = decide(_claim("See (Vaswani et al., 2017)."), catalog)
        assert verdict == "not_checked"
        assert confidence == 0.0
    assert len(calls) == 6


def test_strong_title_match_wins_over_a_catalog_error() -> None:
    catalog = {
        "queried": [
            {
                "catalog": "crossref",
                "status": "match",
                "score": 0.95,
                "title": "Attention Is All You Need",
            },
            {"catalog": "semantic_scholar", "status": "error", "score": 0},
        ]
    }
    verdict, confidence, reason = decide(_claim("See (Vaswani et al., 2017)."), catalog)
    assert verdict == "supported"
    assert confidence >= 0.85
    assert reason == ""
    assert verdict != "unresolved"
