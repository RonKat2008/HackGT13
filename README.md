# PreSearch

A quiet desk for the papers a conference chair is responsible for.

HackGT 13. The screen is **PreSearch**. The build notes call the same product ArxAudit. A chair pastes arXiv ids, or uploads a PDF. The desk reads each paper and keeps the problems a person can open: a citation that does not resolve, a number in the abstract that never appears in the results, a claim with no support, a named dataset that does not resolve, or a public table that does not rerun to the stated figure. Click a finding and the original PDF opens on that sentence.

The output is a reason tied to a passage. It is not a score, and it is not a judgment of the author.

## What a chair does

1. Sign in. The list belongs to that account.
2. Create a conference, or open the one already on the desk.
3. Paste arXiv ids, or upload a PDF.
4. Run the queue. The page stays where it is while each paper is read.
5. Open Summary to watch a paper move from Parse through Stamp.
6. Ask the list a question. Name a paper with `@`. The reply stays tied to that paper.
7. Open a paper. The PDF is in the middle. The checks are beside it.

An author has a separate desk at `/author` for one paper: the same reading, a thread on that paper, and the findings marked on the page.

Type `/Imagine` in the conference thread to ask for a short clip of the list as it stands. The clip is labeled **Generated from this desk. Not a finding.** It does not add a verdict.

## What counts as a finding

| Kind | What failed |
| --- | --- |
| Contradicted | The paper disagrees with itself, or a table does not support the stated difference. |
| Unresolved | Crossref, OpenAlex, and Semantic Scholar all answered, and none matched the citation. |
| Could not reproduce | A named public table was rerun and the number did not match. |
| Insufficient evidence | The claim was checked and still needs a person. |
| Not mentioned | A semantic claim the judge is confident the paper never states. |

A claim that was not checked is not a finding. A likeness score is never a finding. If the abstract-corpus probe’s holdout AUC is under 0.60, that score stays hidden. Copy on the desk does not call a paper fraudulent, and it does not say the paper was written by a model.

A catalog that errors stays **Not checked**. A network failure is not recorded as a missing paper.

## What this does not do

- Label an author, email them, or post a result.
- Retrain the paper’s model or run the paper’s own code.
- Use private video, emergency-call audio, or dispatch logs.
- Treat a high AI-likeness score as a reason to file an issue.

## How a paper is read

Waiting papers are read one after another. Inside a stage, claims of the same kind run together. The stages stay in order:

`parse → claims → evidence → citations → numbers → tables → dataset → reproduce → verify → critic → stamp`

A number contradiction, a table formula, and a finished rerun are final. Lya judges what remains. Jev runs only when Lya is under 0.90. Grok writes the chat reply. Grok does not decide whether a claim holds. The page number comes from searching the PDF, not from a model.

The reproduce step compiles a claim into a small set of operations (count, sum, mean, and related ops) and runs them on a public CSV. Today that table is the Titanic survival set. It does not execute the paper’s code.

Three local papers are built in so a demo does not need the network:

| Id | Paper | What the read should show |
| --- | --- | --- |
| `0000.00001` | Reported Accuracy on a Public Benchmark | The abstract says 95.2%. The results say 61.0%. Smith, 2099 is not a resolvable reference. |
| `0000.00002` | Measured Accuracy on a Public Benchmark | 61.0% appears in the abstract and the results. The citation is in the paper. |
| `0000.00003` | Adaptive Reasoning Systems | The claimed 7.8 point gain is 89.2 − 84.7 = 4.5. Of 891 Titanic passengers, 342 survived. The claim that 317 travelled in first class does not: the table has 216. |

The click path for a live demo is [docs/demo-script.md](docs/demo-script.md).

## Repository

| Path | What it is |
| --- | --- |
| `apps/web` | Next.js screen. Chair desk at `/desk`, author desk at `/author`. |
| `services/orchestrator` | FastAPI checker. PDF parsing, claims, catalogs, table rerun, judge, chat. |
| `packages/schema` | JSON contracts for a batch and a playbook patch. |
| `supabase/migrations` | Shelf, probe, and batch tables. Conference lists live in the checker’s SQLite file. |
| `kaggle` | Notes for the public tables, plus the stored probe result. Downloads stay local. |
| `docs` | Pitch, how the read works, demo script, and the build plans. |

Accounts are Supabase. Conference lists, claims, findings, and chat live in `services/orchestrator/playbook.sqlite`, which is gitignored. A fresh clone has no lists until you create one.

## Run it

You need Node.js current enough for Next 16, Python 3.12, and a copy of the keys. Never put a key in `NEXT_PUBLIC_`. Never commit `.env`.

```bash
cp .env.example .env
```

Fill the root `.env` from [.env.example](.env.example): `XAI_API_KEY`, `OPENROUTER_API_KEY`, `KAGGLE_USERNAME`, `KAGGLE_KEY`, and the Supabase URL and keys. The screen reads a smaller file, `apps/web/.env.local`:

```
SUPABASE_URL=
SUPABASE_PUBLISHABLE_KEY=
ORCHESTRATOR_URL=http://127.0.0.1:8000
```

Do not put the Supabase service role key in `apps/web`. Teammate setup, including the Auth redirect URLs, is in [docs/handoff-person-b.md](docs/handoff-person-b.md).

Screen:

```bash
cd apps/web
npm install
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Checker, in another terminal:

```bash
cd services/orchestrator
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
set -a && source ../../.env && set +a
.venv/bin/uvicorn app:app --app-dir . --host 127.0.0.1 --port 8000
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000). Health check:

```bash
curl -s http://127.0.0.1:8000/health
```

Without `OPENROUTER_API_KEY`, the parsers, citation lookups, and number checks still run. Without `XAI_API_KEY`, chat falls back to a local summary and `/Imagine` does not render a clip.

## Tests

```bash
cd services/orchestrator
.venv/bin/pytest
```

The screen has no separate test runner. `npm run lint` in `apps/web` checks the TypeScript.

## Read next

- [docs/pitch.md](docs/pitch.md) — what to say, and what not to say.
- [docs/how-it-works.md](docs/how-it-works.md) — the eleven stages, with the decision each one makes.
- [docs/summary.md](docs/summary.md) — the checks, the demo papers, and who decides what.
- [docs/demo-script.md](docs/demo-script.md) — the clicks for a live showing.
- [docs/handoff-person-b.md](docs/handoff-person-b.md) — machine setup for a second person.
