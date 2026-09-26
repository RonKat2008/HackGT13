from __future__ import annotations

from models import Patch, PatchStatus


def score(
    n_claims: int,
    n_supported_or_contradicted: int,
    final_status: str,
    rounds: int,
    retry_guard_failed: bool,
) -> float:
    faithful = n_supported_or_contradicted / max(n_claims, 1)
    resolved = 1.0 if str(final_status) != "unresolved" else 0.0
    cheap = 1.0 if rounds == 1 else (0.5 if rounds == 2 else 0.0)
    hack = 1.0 if retry_guard_failed else 0.0
    return 0.5 * faithful + 0.3 * resolved + 0.2 * cheap - 0.6 * hack


def record_result(
    patch: Patch, fitness: float, previous_fitness: float | None
) -> Patch:
    is_win = (
        previous_fitness is None and fitness > 0.0
    ) or (previous_fitness is not None and fitness > previous_fitness)
    if is_win:
        return patch.model_copy(
            update={
                "status": PatchStatus.LIVE,
                "wins": patch.wins + 1,
                "uses": patch.uses + 1,
                "fitness_ema": 0.7 * patch.fitness_ema + 0.3 * fitness,
            }
        )

    losses = patch.losses + 1
    uses = patch.uses + 1
    status = patch.status
    if uses >= 3 and losses > 2 * max(patch.wins, 1):
        status = PatchStatus.ARCHIVED
    return patch.model_copy(
        update={
            "status": status,
            "losses": losses,
            "uses": uses,
            "fitness_ema": 0.7 * patch.fitness_ema + 0.0,
        }
    )
