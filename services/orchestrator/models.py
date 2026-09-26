from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Product(StrEnum):
    STORMCITE = "stormcite"
    LANDFALL = "landfall"


class PatchKind(StrEnum):
    QUERY_TEMPLATE = "query_template"
    PROMPT_RULE = "prompt_rule"
    SPAN_WINDOW = "span_window"
    RETRY_GUARD_BLOCK = "retry_guard_block"


class PatchStatus(StrEnum):
    DRAFT = "draft"
    LIVE = "live"
    ARCHIVED = "archived"


class FinalStatus(StrEnum):
    PASSED = "passed"
    CONTRADICTED = "contradicted"
    UNRESOLVED = "unresolved"


class TestStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_RUN = "not_run"


class TestWhere(StrEnum):
    KAGGLE = "kaggle"
    LOCAL = "local"


class JevLabel(StrEnum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    NOT_MENTIONED = "not_mentioned"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Patch(StrictModel):
    id: UUID
    product: Product
    kind: PatchKind
    target: str = Field(min_length=1)
    trigger: str = Field(min_length=1)
    body: str
    patch_text: str
    status: PatchStatus
    wins: int = Field(ge=0)
    losses: int = Field(ge=0)
    fitness_ema: float
    uses: int = Field(ge=0)


class Claim(StrictModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    type: str = Field(min_length=1)
    evidence_span: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_kind: str = Field(min_length=1)


class TestRecord(StrictModel):
    name: str = Field(min_length=1)
    status: TestStatus
    log_excerpt: str
    where: TestWhere


class JevVerdict(StrictModel):
    claim_id: str = Field(min_length=1)
    label: JevLabel
    confidence: float = Field(ge=0, le=1)
    probs: dict[str, float]


class Budget(StrictModel):
    jev_calls: int = Field(ge=0)
    rounds: int = Field(ge=0)


class Run(StrictModel):
    run_id: UUID
    product: Product
    goal: str = Field(min_length=1)
    goal_hash: str = Field(min_length=1)
    replay_of: UUID | None
    round: int = Field(ge=1, le=3)
    fitness: float
    final_status: FinalStatus
    claims: list[Claim]
    tests: list[TestRecord]
    jev: list[JevVerdict]
    playbook_loaded: list[Patch]
    playbook_patches: list[Patch]
    budget: Budget
