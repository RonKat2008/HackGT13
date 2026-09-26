from __future__ import annotations

import os


def enabled() -> bool:
    return bool(os.environ.get("SUPABASE_URL"))


def record_event(job_id: str, specialist: str, state: str, detail: str) -> None:
    if not enabled():
        return


def save_batch(payload: dict) -> None:
    if not enabled():
        return
