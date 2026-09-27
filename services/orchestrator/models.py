from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Product(StrEnum):
    STORMCITE = "stormcite"
    LANDFALL = "landfall"
    ARXAUDIT = "arxaudit"


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


# Desk verification contract. See docs/contract-verification.md.

STAGES = [
    "parse",
    "claims",
    "evidence",
    "citations",
    "numbers",
    "tables",
    "dataset",
    "reproduce",
    "verify",
    "critic",
    "stamp",
]

# A later judge may name only these. Claim type still comes from the regex in claims.py.
TOOL_NAMES = (
    "search_paper",
    "search_section",
    "search_tables",
    "resolve_citation",
    "numeric_check",
    "resolve_dataset",
    "execute_dataset_claim",
)

# What Lya is allowed to say. The screen keeps the verdict words it already stores.
LYA_VERDICTS = frozenset({"supported", "contradicted", "not_mentioned", "ambiguous"})

NUMBER_LOCK = "Compared the abstract number with the results."
TABLE_LOCK = "Compared the claimed change with the table."


class ClaimType(StrEnum):
    CITATION = "citation"
    NUMERICAL = "numerical"
    NUMERICAL_COMPARISON = "numerical_comparison"
    DATASET = "dataset"
    SEMANTIC = "semantic"


class Verdict(StrEnum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    NOT_MENTIONED = "not_mentioned"
    UNRESOLVED = "unresolved"
    AMBIGUOUS = "ambiguous"
    REPRODUCED = "reproduced"
    COULD_NOT_REPRODUCE = "could_not_reproduce"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NOT_CHECKED = "not_checked"


class Depth(StrEnum):
    CONSISTENCY = "consistency"
    EXTERNAL = "external"
    MATHEMATICAL = "mathematical"
    COMPUTATIONAL = "computational"
    EVIDENCE = "evidence"


class EvidenceRole(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CONTEXT = "context"


class EvidenceSource(StrEnum):
    PAPER = "paper"
    CATALOG = "catalog"
    DATASET = "dataset"
    COMPUTATION = "computation"


FINDING_VERDICTS = frozenset(
    {
        Verdict.CONTRADICTED,
        Verdict.UNRESOLVED,
        Verdict.COULD_NOT_REPRODUCE,
        Verdict.INSUFFICIENT_EVIDENCE,
    }
)
NOT_MENTIONED_FINDING_CONFIDENCE = 0.7


class Evidence(StrictModel):
    page: int | None = None
    section: str = ""
    text: str
    role: EvidenceRole = EvidenceRole.CONTEXT
    source: EvidenceSource = EvidenceSource.PAPER


class ToolEvidence(StrictModel):
    evidence_id: str
    source_type: str
    page: int | None = None
    section: str = ""
    text: str
    metadata: dict = Field(default_factory=dict)


class CatalogQuery(StrictModel):
    catalog: str
    status: str
    candidate_title: str = ""
    doi: str = ""
    score: float = 0.0


class Catalog(StrictModel):
    queried: list[CatalogQuery] = Field(default_factory=list)
    reference: str = ""


class Computation(StrictModel):
    claim_id: str = ""
    dataset_slug: str = ""
    resolution: str = "not_found"
    spec: dict = Field(default_factory=dict)
    actual: float | int | str | None = None
    expected: float | int | str | None = None
    status: str = "could_not_run"
    steps: list[str] = Field(default_factory=list)
    log: str = ""
    formula: str = ""


class DeskClaim(StrictModel):
    claim_id: str = Field(min_length=1)
    job_id: str = ""
    text: str = Field(min_length=1)
    page: int | None = None
    section: str = ""
    claim_type: ClaimType
    verdict: Verdict = Verdict.NOT_CHECKED
    confidence: float = Field(default=0.0, ge=0, le=1)
    depth: Depth = Depth.CONSISTENCY
    rounds: int = Field(default=0, ge=0, le=3)
    reason: str = ""
    evidence: list[Evidence] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    catalog: Catalog | None = None
    computation: Computation | None = None


def deterministic_final(claim: dict) -> bool:
    """A number check, a table formula, or a finished rerun is final. Lya and Jev do not replace it."""
    computation = claim.get("computation") or {}
    if isinstance(computation, dict) and computation.get("status") in {
        "reproduced",
        "could_not_reproduce",
    }:
        return True
    verdict = str(claim.get("verdict") or "")
    steps = [str(step) for step in (claim.get("steps") or [])]
    if verdict == "contradicted" and any(NUMBER_LOCK in step for step in steps):
        return True
    if verdict in {"supported", "contradicted"} and any(TABLE_LOCK in step for step in steps):
        return True
    return False


def is_finding(claim: dict) -> bool:
    verdict = str(claim.get("verdict") or "")
    if verdict in FINDING_VERDICTS:
        return True
    if verdict == Verdict.NOT_MENTIONED and claim.get("claim_type") == ClaimType.SEMANTIC:
        return float(claim.get("confidence") or 0.0) >= NOT_MENTIONED_FINDING_CONFIDENCE
    return False


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
