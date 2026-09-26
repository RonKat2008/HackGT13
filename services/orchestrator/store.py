from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from models import Patch, Run

_ALLOWED_RESULTS = frozenset({"win", "loss"})
_DEFAULT_DB = Path(__file__).resolve().parent / "playbook.sqlite"


def default_db_path() -> Path:
    env = os.environ.get("RUN_DB")
    if env:
        return Path(env)
    return _DEFAULT_DB


def connect(path: str | os.PathLike[str]) -> sqlite3.Connection:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            product TEXT,
            goal TEXT,
            goal_hash TEXT,
            replay_of TEXT,
            "round" INTEGER,
            fitness REAL,
            final_status TEXT,
            json TEXT,
            created_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS patches (
            id TEXT PRIMARY KEY,
            product TEXT,
            kind TEXT,
            target TEXT,
            trigger TEXT,
            body TEXT,
            patch_text TEXT,
            status TEXT,
            wins INTEGER,
            losses INTEGER,
            fitness_ema REAL,
            uses INTEGER,
            created_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS patch_events (
            id TEXT PRIMARY KEY,
            patch_id TEXT,
            run_id TEXT,
            delta_fitness REAL,
            result TEXT
        )
        """
    )
    conn.commit()
    return conn


def insert_run(conn: sqlite3.Connection, run: Run) -> None:
    now = datetime.now(timezone.utc).isoformat()
    payload = run.model_dump(mode="json")
    conn.execute(
        """
        INSERT INTO runs (
            id, product, goal, goal_hash, replay_of, "round",
            fitness, final_status, json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(run.run_id),
            str(run.product),
            run.goal,
            run.goal_hash,
            str(run.replay_of) if run.replay_of is not None else None,
            run.round,
            run.fitness,
            str(run.final_status),
            json.dumps(payload),
            now,
        ),
    )
    conn.commit()


def get_run(conn: sqlite3.Connection, run_id: object) -> Run | None:
    row = conn.execute(
        "SELECT json FROM runs WHERE id = ?",
        (str(run_id),),
    ).fetchone()
    if row is None:
        return None
    return Run.model_validate_json(row["json"])


def save_patch(conn: sqlite3.Connection, patch: Patch) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT OR REPLACE INTO patches (
            id, product, kind, target, trigger, body, patch_text,
            status, wins, losses, fitness_ema, uses, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(patch.id),
            str(patch.product),
            str(patch.kind),
            patch.target,
            patch.trigger,
            patch.body,
            patch.patch_text,
            str(patch.status),
            patch.wins,
            patch.losses,
            patch.fitness_ema,
            patch.uses,
            now,
        ),
    )
    conn.commit()


def list_live_patches(conn: sqlite3.Connection, product: str) -> list[Patch]:
    rows = conn.execute(
        """
        SELECT
            id, product, kind, target, trigger, body, patch_text,
            status, wins, losses, fitness_ema, uses
        FROM patches
        WHERE product = ? AND status = 'live'
        ORDER BY fitness_ema DESC, wins DESC
        """,
        (product,),
    ).fetchall()
    return [Patch.model_validate(dict(row)) for row in rows]


def record_event(
    conn: sqlite3.Connection,
    patch_id: object,
    run_id: object,
    delta_fitness: float,
    result: str,
) -> None:
    if result not in _ALLOWED_RESULTS:
        raise ValueError("result must be win or loss")
    conn.execute(
        """
        INSERT INTO patch_events (id, patch_id, run_id, delta_fitness, result)
        VALUES (?, ?, ?, ?, ?)
        """,
        (str(uuid4()), str(patch_id), str(run_id), delta_fitness, result),
    )
    conn.commit()
