from __future__ import annotations

import hashlib
from uuid import uuid4

from models import (
    Budget,
    Claim,
    FinalStatus,
    JevLabel,
    JevVerdict,
    Product,
    Run,
)
from specialists import run_specialist

MAX_ROUNDS = 3
ACCEPT_CONFIDENCE = 0.8


def fake_jev(claim: Claim) -> JevVerdict:
    supported = "GOOD" in claim.evidence_span and "BAD" not in claim.evidence_span
    return JevVerdict(
        claim_id=claim.id,
        label=JevLabel.SUPPORTED if supported else JevLabel.NOT_MENTIONED,
        confidence=0.9 if supported else 0.4,
        probs={},
    )


def _accepted(verdict: JevVerdict) -> bool:
    return (
        verdict.label in (JevLabel.SUPPORTED, JevLabel.CONTRADICTED)
        and verdict.confidence >= ACCEPT_CONFIDENCE
    )


def _status_if_accepted(verdicts: list[JevVerdict]) -> FinalStatus | None:
    if not verdicts or not all(_accepted(verdict) for verdict in verdicts):
        return None
    if any(verdict.label == JevLabel.CONTRADICTED for verdict in verdicts):
        return FinalStatus.CONTRADICTED
    return FinalStatus.PASSED


def run_loop(goal: str, specialist_name: str = "fixture") -> Run:
    product = Product.STORMCITE
    goal_hash = hashlib.sha256(f"{product}{goal}".encode()).hexdigest()
    round_num = 1
    jev_calls = 0
    claims: list[Claim] = []
    jev: list[JevVerdict] = []
    final_status = FinalStatus.UNRESOLVED

    while True:
        claims = run_specialist(specialist_name, goal, round_num, [])
        jev = [fake_jev(claim) for claim in claims]
        jev_calls += len(jev)
        accepted_status = _status_if_accepted(jev)
        if accepted_status is not None:
            final_status = accepted_status
            break
        if round_num < MAX_ROUNDS:
            round_num += 1
            continue
        final_status = FinalStatus.UNRESOLVED
        break

    return Run(
        run_id=uuid4(),
        product=product,
        goal=goal,
        goal_hash=goal_hash,
        replay_of=None,
        round=round_num,
        fitness=0.0,
        final_status=final_status,
        claims=claims,
        tests=[],
        jev=jev,
        playbook_loaded=[],
        playbook_patches=[],
        budget=Budget(jev_calls=jev_calls, rounds=round_num),
    )
