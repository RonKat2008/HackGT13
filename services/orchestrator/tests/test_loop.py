import hashlib
import inspect
from uuid import UUID

from models import Claim, FinalStatus, JevLabel, JevVerdict, Product
from loop import fake_jev, run_loop


def _claim(evidence_span: str, claim_id: str = "c1") -> Claim:
    return Claim(
        id=claim_id,
        text="A claim about a metric.",
        type="number",
        evidence_span=evidence_span,
        source_id="src-1",
        source_kind="fixture",
    )


def test_no_playbook_ends_round_2_passed():
    run = run_loop("fixture goal")

    assert run.round == 2
    assert run.final_status == FinalStatus.PASSED
    assert run.claims
    assert "GOOD" in run.claims[-1].evidence_span
    assert run.product == Product.STORMCITE
    assert run.goal == "fixture goal"
    assert run.replay_of is None
    assert run.fitness == 0.0
    assert run.playbook_loaded == []
    assert run.playbook_patches == []
    assert run.tests == []
    assert run.budget.rounds == 2
    assert run.budget.jev_calls == 2
    assert len(run.jev) == len(run.claims) == 1
    assert run.jev[0].claim_id == run.claims[0].id
    assert run.jev[0].label == JevLabel.SUPPORTED
    assert run.jev[0].confidence == 0.9
    assert run.jev[0].probs == {}
    assert run.goal_hash == hashlib.sha256(f"{Product.STORMCITE}fixture goal".encode()).hexdigest()
    assert isinstance(run.run_id, UUID)


def test_loop_does_not_use_httpx_or_api_keys():
    import loop

    assert "httpx" not in inspect.getsource(loop)
    run = run_loop("fixture goal")
    assert run.final_status == FinalStatus.PASSED


def test_fake_jev_bad_span_is_not_mentioned():
    verdict = fake_jev(_claim("BAD excerpt"))

    assert verdict.claim_id == "c1"
    assert verdict.label == JevLabel.NOT_MENTIONED
    assert verdict.confidence == 0.4
    assert verdict.probs == {}


def test_fake_jev_good_span_is_supported():
    verdict = fake_jev(_claim("GOOD excerpt"))

    assert verdict.label == JevLabel.SUPPORTED
    assert verdict.confidence == 0.9


def test_fake_jev_otherwise_is_not_mentioned():
    verdict = fake_jev(_claim("plain excerpt with no token"))

    assert verdict.label == JevLabel.NOT_MENTIONED
    assert verdict.confidence == 0.4


def test_retries_same_goal_with_empty_patches(monkeypatch):
    calls: list[tuple[str, str, int, list]] = []

    def spy(name: str, goal: str, round: int, patches: list) -> list[Claim]:
        calls.append((name, goal, round, list(patches)))
        from specialists import run_specialist as real

        return real(name, goal, round, patches)

    monkeypatch.setattr("loop.run_specialist", spy)

    run = run_loop("fixture goal")

    assert run.round == 2
    assert len(calls) == 2
    assert calls[0] == ("fixture", "fixture goal", 1, [])
    assert calls[1] == ("fixture", "fixture goal", 2, [])


def test_unresolved_when_round_3_never_accepted(monkeypatch):
    def always_bad(name: str, goal: str, round: int, patches: list) -> list[Claim]:
        del name, goal, round, patches
        return [_claim("BAD: still missing")]

    monkeypatch.setattr("loop.run_specialist", always_bad)

    run = run_loop("never resolves")

    assert run.round == 3
    assert run.final_status == FinalStatus.UNRESOLVED
    assert run.budget.rounds == 3
    assert run.budget.jev_calls == 3
    assert run.jev[0].label == JevLabel.NOT_MENTIONED


def test_accepted_contradicted_sets_final_status(monkeypatch):
    def one_claim(name: str, goal: str, round: int, patches: list) -> list[Claim]:
        del name, goal, round, patches
        return [_claim("GOOD excerpt")]

    def contradicted(claim: Claim) -> JevVerdict:
        return JevVerdict(
            claim_id=claim.id,
            label=JevLabel.CONTRADICTED,
            confidence=0.85,
            probs={},
        )

    monkeypatch.setattr("loop.run_specialist", one_claim)
    monkeypatch.setattr("loop.fake_jev", contradicted)

    run = run_loop("contradicted goal")

    assert run.round == 1
    assert run.final_status == FinalStatus.CONTRADICTED
    assert run.budget.jev_calls == 1
