from models import Claim, FinalStatus, JevLabel, PatchStatus
from loop import retry_guard_dropped, run_loop, stops


def _claim(text: str, evidence_span: str, claim_id: str = "c1") -> Claim:
    return Claim(
        id=claim_id,
        text=text,
        type="number",
        evidence_span=evidence_span,
        source_id="src-1",
        source_kind="fixture",
    )


def test_stops_supported_low_confidence_is_false():
    assert stops(JevLabel.SUPPORTED, 0.5) is False


def test_stops_supported_high_confidence_is_true():
    assert stops(JevLabel.SUPPORTED, 0.9) is True


def test_stops_not_mentioned_high_confidence_is_false():
    assert stops(JevLabel.NOT_MENTIONED, 0.9) is False


def test_stops_contradicted_high_confidence_is_true():
    assert stops(JevLabel.CONTRADICTED, 0.8) is True


def test_retry_guard_dropped_when_number_missing():
    assert retry_guard_dropped("accuracy 0.81", "accuracy was high") is True


def test_retry_guard_dropped_same_text_is_false():
    assert retry_guard_dropped("accuracy 0.81", "accuracy 0.81") is False


def test_retry_guard_dropped_no_numbers_is_false():
    assert retry_guard_dropped("no number", "still no number") is False


def test_always_bad_specialist_unresolved_at_round_3():
    def always_bad(goal: str, round: int, patches: list) -> list[Claim]:
        del goal, round, patches
        return [_claim("no number", "BAD")]

    run = run_loop("never resolves", specialist=always_bad)

    assert run.round == 3
    assert run.final_status == FinalStatus.UNRESOLVED


def test_retry_guard_keeps_old_claim_and_archives_patch():
    def drop_number(goal: str, round: int, patches: list) -> list[Claim]:
        del goal, patches
        if round == 1:
            return [_claim("accuracy 0.81", "BAD")]
        return [_claim("accuracy was high", "GOOD")]

    run = run_loop("dropped number", specialist=drop_number)

    assert run.claims
    assert "0.81" in run.claims[0].text
    assert run.claims[0].text == "accuracy 0.81"
    assert run.final_status != FinalStatus.PASSED
    assert len(run.playbook_patches) == 1
    assert run.playbook_patches[0].status == PatchStatus.ARCHIVED
