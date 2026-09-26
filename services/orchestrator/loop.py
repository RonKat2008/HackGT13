from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from uuid import uuid4

from models import (
    Budget,
    Claim,
    FinalStatus,
    JevLabel,
    JevVerdict,
    Patch,
    PatchStatus,
    Product,
    Run,
)
from roles import critic
from specialists import run_specialist

MAX_ROUNDS = 3
ACCEPT_CONFIDENCE = 0.8
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def fake_jev(claim: Claim) -> JevVerdict:
    supported = "GOOD" in claim.evidence_span and "BAD" not in claim.evidence_span
    return JevVerdict(
        claim_id=claim.id,
        label=JevLabel.SUPPORTED if supported else JevLabel.NOT_MENTIONED,
        confidence=0.9 if supported else 0.4,
        probs={},
    )


def stops(label: JevLabel, confidence: float) -> bool:
    return label in (JevLabel.SUPPORTED, JevLabel.CONTRADICTED) and confidence >= ACCEPT_CONFIDENCE


def retry_guard_dropped(old_text: str, new_text: str) -> bool:
    return any(number not in new_text for number in _NUMBER.findall(old_text))


def _accepted(verdict: JevVerdict) -> bool:
    return stops(verdict.label, verdict.confidence)


def _status_if_accepted(verdicts: list[JevVerdict]) -> FinalStatus | None:
    if not verdicts or not all(_accepted(verdict) for verdict in verdicts):
        return None
    if any(verdict.label == JevLabel.CONTRADICTED for verdict in verdicts):
        return FinalStatus.CONTRADICTED
    return FinalStatus.PASSED


def _claims_dropped_number(old_claims: list[Claim], new_claims: list[Claim]) -> bool:
    return any(
        retry_guard_dropped(old.text, new.text)
        for old, new in zip(old_claims, new_claims)
    )


def run_loop(
    goal: str,
    specialist_name: str = "fixture",
    specialist: Callable | None = None,
    judge: Callable | None = None,
) -> Run:
    product = Product.STORMCITE
    goal_hash = hashlib.sha256(f"{product}{goal}".encode()).hexdigest()
    round_num = 1
    jev_calls = 0
    claims: list[Claim] = []
    jev: list[JevVerdict] = []
    final_status = FinalStatus.UNRESOLVED
    playbook_patches: list[Patch] = []
    patches: list[Patch] = []
    prev_claims: list[Claim] = []
    pending_patch: Patch | None = None

    def default_specialist(
        specialist_goal: str, specialist_round: int, _applied: list[Patch]
    ) -> list[Claim]:
        return run_specialist(specialist_name, specialist_goal, specialist_round, [])

    specialist_fn = specialist if specialist is not None else default_specialist
    judge_fn = judge if judge is not None else fake_jev

    while True:
        new_claims = specialist_fn(goal, round_num, patches)
        if prev_claims and _claims_dropped_number(prev_claims, new_claims):
            if pending_patch is not None:
                playbook_patches.append(
                    pending_patch.model_copy(update={"status": PatchStatus.ARCHIVED})
                )
                pending_patch = None
            patches = []
            claims = prev_claims
            if round_num < MAX_ROUNDS:
                round_num += 1
                continue
            final_status = FinalStatus.UNRESOLVED
            break

        claims = new_claims
        jev = [judge_fn(claim) for claim in claims]
        jev_calls += len(jev)
        accepted_status = _status_if_accepted(jev)
        if accepted_status is not None:
            final_status = accepted_status
            break
        if round_num < MAX_ROUNDS:
            failed = claims[0]
            label = jev[0].label if jev else JevLabel.NOT_MENTIONED
            pending_patch = critic(failed, label, [specialist_name])
            patches = [pending_patch]
            prev_claims = claims
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
        playbook_patches=playbook_patches,
        budget=Budget(jev_calls=jev_calls, rounds=round_num),
    )
