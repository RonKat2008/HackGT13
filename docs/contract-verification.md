# Verification contract

The desk turns a paper into typed claims, checks each one to a stated depth, and stores a verdict with the evidence that produced it. Both tracks in [plan-verification.md](plan-verification.md) build against this file. Change it only with the other person in the room.

Source of truth in code: `services/orchestrator/models.py` (`DeskClaim`, `Evidence`, `Catalog`, `Computation`, `STAGES`, `is_finding`). Worked example with all twelve claim shapes: `services/orchestrator/fixtures/desk_paper_example.json`.

## Stages

Every paper runs these eleven stages in this order. Each emits a `started` and a `finished` event; a stage that cannot run emits `failed` and the run continues.

| Stage | What it does | Owner step |
| --- | --- | --- |
| `parse` | Open the PDF, count pages, split sections. | A1 (exists) |
| `claims` | Pull typed claims with page numbers. | A2 |
| `evidence` | Retrieve supporting and contradicting passages per claim. | A3 |
| `citations` | Match in-text tokens to references, then resolve references in external catalogs. | A6 |
| `numbers` | Check numbers stated in one section against the others. | exists |
| `tables` | Read tables and check derived numbers (differences, percent changes). | A7 |
| `dataset` | Name the public dataset a claim depends on and resolve it. | B3 |
| `reproduce` | Compile a dataset claim to a spec, download the table, execute. | B2, B4 |
| `verify` | Jev judges each claim against its evidence with a confidence. | A4 |
| `critic` | Bounded retry with typed patches for uncertain verdicts. | A5 |
| `stamp` | Collapse duplicates, write claims and issues, set the paper verdict. | exists |

## Claim

```json
{
  "claim_id": "sha1(job_id + text)[:12]",
  "job_id": "…",
  "text": "sentence as written in the paper",
  "page": 4,
  "section": "abstract | methods | results | discussion | references | body",
  "claim_type": "citation | numerical | numerical_comparison | dataset | semantic",
  "verdict": "see below",
  "confidence": 0.0,
  "depth": "consistency | external | mathematical | computational | evidence",
  "rounds": 0,
  "reason": "one sentence a chair can read",
  "evidence": [Evidence],
  "steps": ["what the desk did, in order"],
  "catalog": Catalog | null,
  "computation": Computation | null
}
```

`Evidence`: `{page, section, text, role: supports|contradicts|context, source: paper|catalog|dataset|computation}`.

`Catalog`: `{queried: [{catalog, status, candidate_title, doi, score}], reference}`.

`Computation`: `{claim_id, dataset_slug, resolution: match|ambiguous|not_found, spec, actual, expected, status: reproduced|could_not_reproduce|could_not_run, steps, log, formula}`.

Models forbid extra fields. Nothing about AI likeness lives on a claim.

## Verdicts

Stored value → word on screen.

| Stored | Screen | Used by |
| --- | --- | --- |
| `supported` | Supported | citations, numbers, semantic |
| `contradicted` | Contradicted | numbers, tables, semantic |
| `not_mentioned` | Not found | semantic |
| `unresolved` | Unresolved | citations |
| `ambiguous` | Ambiguous | dataset resolution |
| `reproduced` | Reproduced | dataset |
| `could_not_reproduce` | Could not reproduce | dataset, tables |
| `insufficient_evidence` | Insufficient evidence · Requires human review | critic cap reached |
| `not_checked` | Not checked | no key, no network, no data |

A **finding** is a claim whose verdict is `contradicted`, `unresolved`, `could_not_reproduce`, or `insufficient_evidence`, plus a `semantic` claim that is `not_mentioned` with confidence ≥ 0.70. `ambiguous` and `not_checked` are never findings. Paper verdict: `Verified` when the finding count is zero, else `N findings`.

Unresolved citation wording: "The reference could not be independently resolved in the catalogs searched." Never write fraudulent, fake, fabricated, or AI-written anywhere.

## Summary

Attached to every paper in `paper_desk` and `conference_desk`:

```json
{
  "analyzed": 12,
  "supported": 4,
  "contradicted": 2,
  "unresolved": 1,
  "not_reproduced": 1,
  "insufficient": 1,
  "categories": {
    "citations":     {"resolved": 1,   "total": 2},
    "internal":      {"supported": 1,  "total": 3},
    "numerical":     {"consistent": 1, "total": 4},
    "computational": {"reproduced": 1, "total": 3}
  }
}
```

`supported` counts `supported` and `reproduced`. `internal` is the semantic claims. `numerical` is `numerical` and `numerical_comparison`. `computational` is the dataset claims. `conference_desk` papers also carry `finding_count`.

## Storage

- `paper_claims (claim_id, job_id, position, text, page, section, claim_type, verdict, confidence, depth, rounds, reason, evidence_json, catalog_json, computation_json, steps_json)`, primary key `(job_id, claim_id)`.
- `paper_issues` gains `claim_id, confidence, depth, verdict` so the existing report and UI keep working while the claims land.
- Both are created or migrated by `desk._ensure_desk`.

## Seams

- `paper_audit.audit_paper(path, job_id, recorder=, repro=) -> {issues, claims, events, kaggle, hidden, section_quality}`.
- `repro.reproduce(claims, sections) -> list[Computation dict]` (B4). Until B4 lands the old dict return is tolerated by the `reproduce` stage.
- `verify.judge(claim, evidence) -> (verdict, confidence)` (A4).
- `references.resolve(reference_text) -> Catalog` (A6).
- `dsl.execute(spec, frame) -> Computation` (B2).

## Local fixtures

| arXiv id | File | Author | Purpose |
| --- | --- | --- | --- |
| `0000.00001` | `fixtures/hallucinated.pdf` | Ada Example | citation and number contradictions |
| `0000.00002` | `fixtures/human.pdf` | Lin Example | passes clean |
| `0000.00003` | `fixtures/demo_paper.pdf` | Mira Example | the demo: every verdict at least once (B1) |
