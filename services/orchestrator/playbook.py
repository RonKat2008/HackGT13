from __future__ import annotations

import sqlite3

from models import Patch, PatchKind, PatchStatus
from store import list_live_patches

_APPLY_STATUSES = frozenset({PatchStatus.DRAFT, PatchStatus.LIVE})
_SPAN_WINDOWS = frozenset({"neighbors:1", "neighbors:2"})


def apply(patches: list[Patch], specialist_name: str) -> tuple[str, list[str]]:
    query_parts: list[str] = []
    extra_prompt_lines: list[str] = []
    for patch in patches:
        if patch.target != specialist_name:
            continue
        if patch.status not in _APPLY_STATUSES:
            continue
        if patch.kind == PatchKind.QUERY_TEMPLATE:
            if "{" in patch.body:
                query_parts.append(patch.body)
        elif patch.kind == PatchKind.PROMPT_RULE:
            extra_prompt_lines.append(patch.body[:200])
        elif patch.kind == PatchKind.SPAN_WINDOW:
            if patch.body in _SPAN_WINDOWS:
                extra_prompt_lines.append(patch.body)
    return " ".join(query_parts), extra_prompt_lines


def top_patches(conn: sqlite3.Connection, product: str, n: int = 5) -> list[Patch]:
    return list_live_patches(conn, product)[:n]


def accept_patch(patch: Patch) -> Patch:
    if patch.kind == PatchKind.QUERY_TEMPLATE and "{" not in patch.body:
        raise ValueError("query_template body must contain a {token}")
    return patch
