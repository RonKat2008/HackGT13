# Why reproduce and verify were slow

The desk process does not reload code. A conference that is already running stays on the process that started it. The next API start is what picks this up.

## What changed

Reproduce, in `services/orchestrator/datasets.py` and `services/orchestrator/repro.py`:

- A `word/word` token is not a Kaggle dataset. Year spans are ignored. Any other `owner/name` counts only when that same sentence says Kaggle. The Titanic catalog entry still counts.
- The paper is scanned once. If it does not name a catalog table or a Kaggle slug, reproduce returns without calling Grok.
- On the audit path, a sentence is compiled with the local patterns unless the caller passed a model. `ask=None` no longer means "call Grok".
- `kaggle datasets list` is not used to guess a table. `kaggle datasets download` runs only for a catalog slug. A file already on disk can still be read. An unknown slug is `could_not_run` without a CLI wait.
- One slug is downloaded at most once per paper.

Verify, in `services/orchestrator/lya.py` and `services/orchestrator/verify.py`:

- Lya's API checks for one paper run four at a time. A local Lya batch is unchanged.
- Jev calls for the same kind of claim run four at a time. A number that already looks contradicted still finishes before an ordinary sentence starts.
- Lya's accept bar stays 0.90. A claim Lya accepts never goes to Jev.
- An ordinary claim gets one Jev call. Rounds two and three stay only for a contradicted-looking number or an unresolved citation, and only when the tool pass added a new evidence line.

## Why it was slow

Reproduce sits in the same pool as evidence, citations, numbers, tables, and dataset. Verify cannot start until that pool finishes. The old path treated every "samples" sentence as a table check, called Grok when the local pattern missed (30 seconds each), and could then run `kaggle datasets list` (20 seconds) and `kaggle datasets download` (up to 120 seconds).

Verify's cost is the number of model calls. The default Lya model is `grok-4.6`, up to 40 claims, and anything under 0.90 goes to Jev. A `not_mentioned` result used to open two more Jev rounds. Four-wide overlap does not remove those calls. Skipping the extra rounds on ordinary claims does.
