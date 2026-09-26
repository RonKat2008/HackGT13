from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from models import Claim, Patch

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "fail_then_pass.json"

Specialist = Callable[[str, int, list[Patch]], list[Claim]]


class SpecialistNotFound(KeyError):
    """Raised when run_specialist is given a name that is not registered."""


def _load_fixture_spans() -> dict[str, str]:
    return json.loads(FIXTURE_PATH.read_text())


def fixture_specialist(goal: str, round: int, patches: list[Patch]) -> list[Claim]:
    del goal
    spans = _load_fixture_spans()
    use_good = round == 2 or any(
        patch.kind == "query_template" and "{metric}" in patch.body for patch in patches
    )
    evidence_span = spans["good_span"] if use_good else spans["bad_span"]
    return [
        Claim(
            id="fixture-claim-1",
            text="The paper reports the requested metric in the results section.",
            type="number",
            evidence_span=evidence_span,
            source_id="fail_then_pass",
            source_kind="fixture",
        )
    ]


SPECIALISTS: dict[str, Specialist] = {
    "fixture": fixture_specialist,
}


def run_specialist(name: str, goal: str, round: int, patches: list[Patch]) -> list[Claim]:
    try:
        specialist = SPECIALISTS[name]
    except KeyError as exc:
        raise SpecialistNotFound(name) from exc
    return specialist(goal, round, patches)
