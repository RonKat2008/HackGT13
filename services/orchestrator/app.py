from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from batches import (
    BatchError,
    create_batch,
    create_conference,
    get_batch,
    get_conference,
    patch_paper,
)
from fitness import record_result, score
from loop import run_loop
from models import JevLabel, Patch, PatchKind, PatchStatus, Product, Run
from playbook import top_patches
from specialists import run_specialist
from store import connect, default_db_path, get_run, insert_run, record_event, save_patch

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateRunBody(BaseModel):
    product: Product
    goal: str = Field(min_length=1)
    fixture: bool


class CreateBatchBody(BaseModel):
    product: str
    kind: str
    name: str | None
    arxiv_ids: list[str]
    conference_id: str | None = None


class CreateConferenceBody(BaseModel):
    name: str = Field(min_length=1)
    contact_email: str = Field(min_length=1)


class PatchPaperBody(BaseModel):
    author_email: str | None = None
    contacted_at: str | None = None


def _batch_http(exc: BatchError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@contextmanager
def _db() -> Iterator:
    conn = connect(default_db_path())
    try:
        yield conn
    finally:
        conn.close()


def _score_run(run: Run, retry_guard_failed: bool = False) -> float:
    n_supported = sum(
        1
        for verdict in run.jev
        if verdict.label in (JevLabel.SUPPORTED, JevLabel.CONTRADICTED)
    )
    return score(
        n_claims=len(run.claims),
        n_supported_or_contradicted=n_supported,
        final_status=str(run.final_status),
        rounds=run.round,
        retry_guard_failed=retry_guard_failed,
    )


def _live_fixture_patch(product: Product, fitness: float) -> Patch:
    draft = Patch(
        id=uuid4(),
        product=product,
        kind=PatchKind.QUERY_TEMPLATE,
        target="fixture",
        trigger="not_mentioned",
        body="{metric} results",
        patch_text="Search the results section for the metric.",
        status=PatchStatus.DRAFT,
        wins=0,
        losses=0,
        fitness_ema=0.0,
        uses=0,
    )
    return record_result(draft, fitness, None)


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/runs")
def create_run(body: CreateRunBody) -> Run:
    if not body.fixture:
        raise HTTPException(status_code=400, detail="only fixture runs are supported")
    run = run_loop(body.goal)
    fitness_value = _score_run(run)
    live_patch = _live_fixture_patch(body.product, fitness_value)
    stored = run.model_copy(
        update={
            "product": body.product,
            "fitness": fitness_value,
            "playbook_patches": [live_patch],
        }
    )
    with _db() as conn:
        insert_run(conn, stored)
        save_patch(conn, live_patch)
        record_event(conn, live_patch.id, stored.run_id, fitness_value, "win")
    return stored


@app.get("/runs/{run_id}")
def read_run(run_id: UUID) -> Run:
    with _db() as conn:
        run = get_run(conn, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@app.post("/runs/{run_id}/replay")
def replay_run(run_id: UUID) -> Run:
    with _db() as conn:
        parent = get_run(conn, run_id)
        if parent is None:
            raise HTTPException(status_code=404, detail="run not found")
        live = top_patches(conn, str(parent.product))

        def injected(goal: str, round_num: int, patches: list[Patch]) -> list:
            return run_specialist("fixture", goal, round_num, live + patches)

        new_run = run_loop(parent.goal, specialist=injected)
        fitness_value = _score_run(new_run)
        stored = new_run.model_copy(
            update={
                "product": parent.product,
                "fitness": fitness_value,
                "replay_of": parent.run_id,
                "playbook_loaded": live,
            }
        )
        insert_run(conn, stored)
        return stored


@app.get("/playbook")
def list_playbook(product: Product) -> list[Patch]:
    with _db() as conn:
        return top_patches(conn, str(product))


@app.post("/voice/token")
def voice_token() -> None:
    raise HTTPException(status_code=501, detail="not implemented")


@app.post("/batches")
def post_batch(body: CreateBatchBody) -> dict:
    try:
        return create_batch(body.model_dump())
    except BatchError as exc:
        _batch_http(exc)


@app.get("/batches/{batch_id}")
def read_batch(batch_id: str) -> dict:
    try:
        return get_batch(batch_id)
    except BatchError as exc:
        _batch_http(exc)


@app.post("/conferences")
def post_conference(body: CreateConferenceBody) -> dict:
    try:
        return create_conference(body.model_dump())
    except BatchError as exc:
        _batch_http(exc)


@app.get("/conferences/{conference_id}")
def read_conference(conference_id: str) -> dict:
    try:
        return get_conference(conference_id)
    except BatchError as exc:
        _batch_http(exc)


@app.patch("/papers/{job_id}")
def update_paper(job_id: str, body: PatchPaperBody) -> dict:
    try:
        return patch_paper(job_id, body.model_dump())
    except BatchError as exc:
        _batch_http(exc)

