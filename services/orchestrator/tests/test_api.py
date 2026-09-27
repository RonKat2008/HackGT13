from fastapi.testclient import TestClient

import voice
from app import app


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "playbook.sqlite"))
    return TestClient(app)


def _create_fixture(client: TestClient, goal: str = "check the metric") -> dict:
    response = client.post(
        "/runs",
        json={"product": "stormcite", "goal": goal, "fixture": True},
    )
    assert response.status_code == 200
    return response.json()


def test_health_still_returns_ok(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_create_fixture_run_scores_fitness_and_saves_live_patch(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    body = _create_fixture(client)

    assert body["round"] == 2
    assert body["budget"]["rounds"] == 2
    assert body["final_status"] == "passed"
    assert body["fitness"] == 0.9
    assert body["product"] == "stormcite"
    assert body["goal"] == "check the metric"
    assert body["replay_of"] is None
    assert body["playbook_loaded"] == []
    assert len(body["playbook_patches"]) == 1
    patch = body["playbook_patches"][0]
    assert patch["kind"] == "query_template"
    assert patch["target"] == "fixture"
    assert patch["trigger"] == "not_mentioned"
    assert patch["status"] == "live"
    assert "{metric}" in patch["body"]
    assert patch["body"] == "{metric} results"
    assert len(body["claims"]) == 1
    assert body["jev"][0]["label"] == "supported"


def test_get_run_returns_stored_json_including_fitness(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    created = _create_fixture(client)
    run_id = created["run_id"]

    response = client.get(f"/runs/{run_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == run_id
    assert body["fitness"] == 0.9
    assert "playbook_loaded" in body
    assert body["playbook_loaded"] == []
    assert body["playbook_patches"][0]["status"] == "live"


def test_get_unknown_run_is_404(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.get("/runs/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")

    assert response.status_code == 404


def test_fixture_false_returns_400(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/runs",
        json={"product": "stormcite", "goal": "live run", "fixture": False},
    )

    assert response.status_code == 400


def test_replay_finishes_round_1_with_loaded_metric_patch(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    parent = _create_fixture(client)

    response = client.post(f"/runs/{parent['run_id']}/replay")

    assert response.status_code == 200
    replay = response.json()
    assert replay["round"] == 1
    assert replay["budget"]["rounds"] == 1
    assert replay["replay_of"] == parent["run_id"]
    assert replay["goal"] == parent["goal"]
    assert replay["fitness"] >= parent["fitness"]
    loaded = replay["playbook_loaded"]
    assert any(
        patch["kind"] == "query_template" and "{metric}" in patch["body"]
        for patch in loaded
    )


def test_replay_unknown_run_is_404(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.post("/runs/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/replay")

    assert response.status_code == 404


def test_get_playbook_returns_live_patches(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _create_fixture(client)

    response = client.get("/playbook", params={"product": "stormcite"})

    assert response.status_code == 200
    patches = response.json()
    assert isinstance(patches, list)
    assert len(patches) >= 1
    assert all(patch["status"] == "live" for patch in patches)
    assert any(
        patch["kind"] == "query_template" and "{metric}" in patch["body"]
        for patch in patches
    )


def test_voice_token_without_a_key_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    client = _client(tmp_path, monkeypatch)

    response = client.post("/voice/token")

    assert response.status_code == 503
    assert "XAI_API_KEY" not in response.text


def test_voice_token_returns_the_client_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "test-xai-key")
    monkeypatch.setattr(voice, "client_secret", lambda: {"value": "ephemeral", "expires_at": 10})
    client = _client(tmp_path, monkeypatch)

    response = client.post("/voice/token")

    assert response.status_code == 200
    assert response.json() == {"value": "ephemeral", "expires_at": 10}
    assert "test-xai-key" not in response.text


def test_cors_allows_localhost_3000(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.get("/health", headers={"Origin": "http://localhost:3000"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
