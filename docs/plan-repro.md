# Fast reproduction layer

Source brief: `/Users/sohaibqurashi/Documents/ArxAudit_Fast_Reproduction_Layer_Refactor.md`. Friend’s cuts: [docs/speed-notes.md](speed-notes.md). Desk contract: [docs/plan-throughput.md](plan-throughput.md).

The chair desk, Lya-then-Jev, and the fixture papers stay. This plan makes computational checks cheap: resolve a table once, compile typed specs, execute locally in a batch, and keep Jev off a clear match or mismatch.

```text
Models compile and interpret. Deterministic systems execute.
Datasets are resolved once, loaded once, cached, and reused.
```

Follow [AGENTS.md](../AGENTS.md): one subagent per step, verify, then continue. This track edits `services/orchestrator` only. Do not edit `apps/web`. Do not start Landfall. Do not retrain Lya. Do not raise `LYA_THRESHOLD`. Do not send every claim to Jev. Do not say fake, fraudulent, fabricated, or AI-written. Agents do not edit their own source to make a run pass. Do not write model-generated Python. Do not add `CORRELATION` as free Python — only as a later typed DSL op if a step names it.

Do not commit. Do not push.

## What already exists

Do not rebuild these.

- Local DSL in [services/orchestrator/dsl.py](../services/orchestrator/dsl.py): `ROWS`, `COUNT`, `COUNT_EQ`, `SUM`, `MEAN`, `MEDIAN`, `MIN`, `MAX`, `PERCENT`, `DIFFERENCE`, `PERCENT_CHANGE`. Pandas execute. No arbitrary Python.
- Sentence compiler in [services/orchestrator/compiler.py](../services/orchestrator/compiler.py). Patterns first. A model JSON is accepted only as `dsl.Spec`.
- Dataset cache in [services/orchestrator/datasets.py](../services/orchestrator/datasets.py): `lookup_table` / `remember_table` / `acquire_table`. One slug downloads at most once per paper. Unknown slugs do not call the CLI. Jev only breaks a two-candidate tie.
- [services/orchestrator/repro.py](../services/orchestrator/repro.py) runs locally. `push_kernel` is off unless `ARX_KAGGLE_KERNEL=1`. Grok is not called on the audit path (`ask` is a no-op).
- Numbers and tables already settle paper-internal arithmetic before reproduce starts.
- Titanic lock: 342 reproduced, 317 is 216, 891 rows, mean Age 29.7, mean Fare 80.0 fails.

What is still slow or missing:

- `reproduce()` walks dataset sentences one by one, resolves each, and `read_csv`s the same path again.
- No `ReproSpec` wrapper, no DuckDB, no batched SQL, no parallel dataset groups, no result cache, no skip when a claim is already settled internally.

## Shared contract

Field names freeze after R0. A computation dict on a claim still uses `status` `reproduced` | `could_not_reproduce` | `could_not_run`. Add optional timing keys. Older clients ignore them.

### `ReproSpec`

```text
claim_id, dataset_id, file_id, operation, column, filters, arguments, expected,
comparison: {type: "EXACT"|"TOLERANCE", tolerance: number|null}, sentence
```

`filters` start empty. `arguments` holds `equals` / `value` for `COUNT_EQ`. Reject unknown operations before execute.

### Eligibility statuses

`NOT_REQUIRED` | `NOT_EXECUTABLE` | `DATASET_NOT_FOUND` | `DATASET_AMBIGUOUS` | `UNSUPPORTED_OPERATION`

These are logs / `could_not_run` reasons. They are not new verdict words on the desk.

## Rules that still bind

- Deterministic number, table, and rerun verdicts stay final.
- Restricted DSL only. No model-written Python.
- Kaggle is download/discovery. Not the compute engine. Kernel push stays behind `ARX_KAGGLE_KERNEL=1`.
- Jev does not compare 342 vs 342 or 95.2 vs 61.0.
- Public data only. Keys stay server-side.
- `0000.00001` still fails, `0000.00002` still Verified, Adaptive still shows 95.2, 7.8, 317 vs 216, and 342 reproduced.

## Steps

### R0 — Freeze ReproSpec

- Subagent: `generalPurpose`
- Files: [services/orchestrator/repro_spec.py](../services/orchestrator/repro_spec.py) (new), [services/orchestrator/tests/test_repro_spec.py](../services/orchestrator/tests/test_repro_spec.py) (new).
- Do:
  1. Add `ReproSpec` matching the Shared contract. Build it from a `dsl.Spec` plus `claim_id` and `dataset_id`.
  2. Reject an unknown operation and a missing `COUNT_EQ` value.
  3. Unit test field names. No audit, no network, no DuckDB yet.
- Verify: `services/orchestrator/.venv/bin/python -m pytest tests/test_repro_spec.py -q`
- Pass: exits 0.

### R1 — Skip claims the paper already settled

- Subagent: `generalPurpose`
- Depends on: R0
- Files: [services/orchestrator/repro.py](../services/orchestrator/repro.py), [services/orchestrator/tests/test_repro.py](../services/orchestrator/tests/test_repro.py).
- Do:
  1. A claim whose verdict is already `contradicted`, `supported`, `reproduced`, or `could_not_reproduce` from numbers/tables does not enter external reproduce. Status `NOT_REQUIRED`.
  2. A sentence that is not computationally verifiable stays out (`NOT_EXECUTABLE`). Keep the existing “samples” / unknown-slug guards.
  3. Test: a 7.8-style claim already marked `contradicted` does not call `acquire_table` / `download_table`. Demo Titanic sentences still compile.
- Verify: `services/orchestrator/.venv/bin/python -m pytest tests/test_repro.py tests/test_compiler.py -q`
- Pass: exits 0. 342 and 317 still recorded on the demo fixture.

### R2 — Group by dataset and load once

- Subagent: `generalPurpose`
- Depends on: R1
- Files: [services/orchestrator/repro.py](../services/orchestrator/repro.py), [services/orchestrator/tests/test_repro.py](../services/orchestrator/tests/test_repro.py).
- Do:
  1. Compile every eligible sentence first. Resolve slugs. Group specs by `dataset_id`.
  2. `acquire_table` once per slug. Load the frame once into a `ReproductionContext`.
  3. Execute every spec for that slug against the same loaded table. Do not `read_csv` per claim.
  4. Test: three Titanic claims, patched loader is called once. 891 / 342 / 317 still correct.
- Verify: `services/orchestrator/.venv/bin/python -m pytest tests/test_repro.py tests/test_datasets.py -q`
- Pass: exits 0.

### R3 — DuckDB for the hot ops

- Subagent: `generalPurpose`
- Depends on: R2
- Files: [services/orchestrator/duck_repro.py](../services/orchestrator/duck_repro.py) (new), [services/orchestrator/requirements.txt](../services/orchestrator/requirements.txt) (`duckdb` only), [services/orchestrator/repro.py](../services/orchestrator/repro.py) (call the engine), [services/orchestrator/tests/test_duck_repro.py](../services/orchestrator/tests/test_duck_repro.py) (new).
- Do:
  1. Install `duckdb` into `services/orchestrator/.venv`.
  2. Compile `ROWS`, `COUNT_EQ`, `SUM`, `MEAN`, `MEDIAN`, `MIN`, `MAX` to parameterized SQL. Identifiers are allowlisted columns only.
  3. `ReproductionContext` prefers DuckDB. Pandas `dsl.execute` stays the fallback if DuckDB is missing.
  4. Test: Titanic CSV — 891 rows, 342 survived, 216 first class vs claimed 317. No network.
- Verify: `services/orchestrator/.venv/bin/python -m pytest tests/test_duck_repro.py tests/test_dsl.py tests/test_repro.py -q`
- Pass: exits 0.

### R4 — Batch compatible aggregations

- Subagent: `generalPurpose`
- Depends on: R3
- Files: [services/orchestrator/duck_repro.py](../services/orchestrator/duck_repro.py), [services/orchestrator/tests/test_duck_repro.py](../services/orchestrator/tests/test_duck_repro.py).
- Do:
  1. Specs on one table that are filter-free `ROWS` / `MEAN` / `SUM` / `COUNT` compile into one `SELECT`.
  2. `COUNT_EQ` may stay its own `WHERE` query when it cannot share the scan cleanly.
  3. Test: ROWS + MEAN(Age) on Titanic is one SQL string with both `count(*)` and `avg`. Results still 891 and 29.7.
- Verify: `services/orchestrator/.venv/bin/python -m pytest tests/test_duck_repro.py tests/test_repro.py -q`
- Pass: exits 0.

### R5 — Parallel independent datasets

- Subagent: `generalPurpose`
- Depends on: R4
- Files: [services/orchestrator/repro.py](../services/orchestrator/repro.py) (group execute only), [services/orchestrator/tests/test_repro.py](../services/orchestrator/tests/test_repro.py).
- Do:
  1. Different `dataset_id` groups run under a pool (`REPRO_WORKERS`, default 2, cap 4).
  2. Specs that share a dataset stay on one worker.
  3. Test: two slugs, a latch proves the second group starts before the first execute returns.
- Verify: `services/orchestrator/.venv/bin/python -m pytest tests/test_repro.py -q`
- Pass: exits 0. Titanic still 342 / 216.

### R6 — Cache observed results

- Subagent: `generalPurpose`
- Depends on: R5
- Files: [services/orchestrator/datasets.py](../services/orchestrator/datasets.py) (fingerprint + result table), [services/orchestrator/repro.py](../services/orchestrator/repro.py) (lookup/store), [services/orchestrator/tests/test_repro_cache.py](../services/orchestrator/tests/test_repro_cache.py) (new).
- Do:
  1. Fingerprint a table by slug, file size, mtime, and column names.
  2. Cache key: fingerprint + ReproSpec hash + engine version `repro-1`.
  3. Store observed number and status. Do not cache a download error as a verdict.
  4. Test: second call with the same CSV does not re-run the engine (patch execute and assert not called).
- Verify: `services/orchestrator/.venv/bin/python -m pytest tests/test_repro_cache.py tests/test_datasets.py tests/test_repro.py -q`
- Pass: exits 0.

### R7 — Timing fields

- Subagent: `generalPurpose`
- Depends on: R6
- Files: [services/orchestrator/repro.py](../services/orchestrator/repro.py), [services/orchestrator/tests/test_repro.py](../services/orchestrator/tests/test_repro.py).
- Do:
  1. Each computation may include `dataset_resolution_ms`, `dataset_load_ms`, `execution_ms`, `comparison_ms`, `cache_hit`.
  2. No secrets. No trust score.
  3. Test: a local Titanic run sets those keys. `cache_hit` is true on the second identical spec after R6.
- Verify: `services/orchestrator/.venv/bin/python -m pytest tests/test_repro.py tests/test_repro_cache.py tests/test_paper_audit.py -q`
- Pass: exits 0. Demo paper still stamps 317 vs 216.

## Build order

```text
R0 → R1 → R2 → R3 → R4 → R5 → R6 → R7
```

Serial. File lists overlap on `repro.py`. Do not run two steps at once.

P2 from the brief (alias search, semantic column mapping, adaptive priority) is not this file. Stop after R7.

## Done when

- The same Titanic CSV is acquired once per paper and loaded once per slug.
- Three claims on that table execute in one context (DuckDB batch when they can share a scan).
- A claim already settled by a table formula does not download a dataset.
- Kaggle is not the execute engine. Kernel push stays opt-in.
- Jev is not called for 342 == 342 or 317 vs 216.
- A second identical spec against the same file bytes hits the result cache.
- `0000.00001` still fails, `0000.00002` still Verified, Adaptive still shows 95.2, 7.8, 317 vs 216, and 342 reproduced.

## What not to do

- One remote Kaggle kernel per claim.
- `read_csv` per claim on the same path.
- Jev on a clear numeric match or mismatch.
- Model-written Python.
- Raising `LYA_THRESHOLD` or sending every claim to Jev.
- Editing `apps/web` in this plan.
- Committing or pushing.
