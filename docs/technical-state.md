# ArxAudit technical state

Written 26 Sep 2026 for a brainstorm. This describes the repo as it is, the problem the product is aimed at, and the gap between the original technical plan and the desk a chair can run. It is not a pitch. Shared product language is in `docs/pitch.md`. Laptop setup is in `docs/handoff-person-b.md`.

HackGT 13. Submissions close 27 Sep 2026, 12:00pm EDT. Product is ArxAudit. Landfall is not being built. The old name StormCite is retired.

Person A owns `services/orchestrator`, schema, and Supabase SQL. Person B owns `apps/web` and `kaggle/`.

## The problem, with the evidence

The product exists because hallucinated citations have entered the published record, and the rate rose after people started drafting papers with language models. Peer review is missing them because a fake reference is formatted, attributed to a real person, and still points at no publication.

Figures below are from the papers, not from this repo. Timing is consistent with LLM writing. The papers themselves say the timing is not proof that every fabricated reference was produced by a model. Paper mills and indexing changes are also in the record.

- **Biomedical literature.** A Lancet audit of about 2.5 million papers and 97.1 million references found 4,046 fabricated references across 2,810 papers. About 1 in 2,828 papers had one in 2023, 1 in 458 in 2025, and 1 in 277 in the first seven weeks of 2026. The rate rose more than twelvefold, from about 4 per 10,000 papers in 2023 to 51.3 per 10,000 in Q4 2025 and 56.9 per 10,000 in early 2026. The curve bends in mid-2024, about one publication cycle after widespread model use. Review articles were higher than other types. Most affected papers had one or two fabricated references. The same author pair showed up across 11 papers in one journal with repeated fabricated references. Prior studies cited there estimate that 30–69% of LLM-generated biomedical references are fabricated. Source: *Fabricated citations: an audit across 2.5 million biomedical papers*, The Lancet, 2026.
- **Preprints and journals together.** An audit of 111 million references across 2.5 million papers on arXiv, bioRxiv, SSRN, and PubMed Central estimates 146,932 hallucinated citations in 2025 alone. The rate is higher in fields that adopted AI writing quickly, in manuscripts with linguistic signs of AI-assisted writing, and among small and early-career teams. Preprint moderation and journal publication catch only a fraction. Hallucinated references disproportionately credit already prominent and male scholars. Source: arXiv:2605.07723, *LLM hallucinations in the wild*.
- **ACL venues.** Papers with at least one hallucinated citation went from 20 in 2024 to 281 in 2025. The share went from about 0.28% to 2.65%, and to 3.84% at EMNLP 2025. EMNLP 2025 alone accounts for 160 papers, and more than 100 of those were in the main conference or Findings, not only workshops. Source: *HalluCitation Matters*, ACL 2026 long paper.
- **ML and security venues.** In 2025, the share of accepted papers with at least two likely hallucinated academic-paper-like references was about 1.9% at ICLR, 3.4% at ICML, 5.1% at NeurIPS, and 4.8% at USENIX Security. That is roughly 1 in 20 accepted NeurIPS papers and a similar share of USENIX Security papers under that paper’s strict definition. Rates rise in the post-ChatGPT window. Some of those citations are in award-winning papers. Source: arXiv:2607.00738, *Phantom References*.

What those studies count is a reference that does not correspond to a real work. What the desk counts today is narrower. See “The honesty gap” below.

## What the original technical plan was

The shared orchestrator plan (`docs/plan-orchestrator.md`) is a recursive harness. “Recursive” does not mean the agents rewrite their own Python. That is forbidden. It means a playbook of typed patches.

Two clocks:

1. **Inside one run.** Specialists retrieve evidence. Jev judges a claim against that text and may only answer `supported`, `contradicted`, or `not_mentioned`, plus a confidence. If Jev says `not_mentioned` or confidence is low, a critic emits one patch. The same paper is read again, at most three rounds.
2. **Across runs.** Fitness scores the run. A patch that raises fitness stays live. A patch that lowers fitness is archived. A patch that makes a finding vanish by deleting the citation, the number, or the claim is blocked. The next paper loads the five best live patches before the first specialist. `POST /runs/{id}/replay` reruns one goal with the updated playbook.

Patch kinds are only `query_template`, `prompt_rule`, and `span_window`.

Models in that plan:

- **Grok** writes prose and can plan. It does not decide whether a claim is true.
- **Jev** (`typesafe/jev-1.13` on OpenRouter Decisions, `POST https://openrouter.ai/api/alpha/decisions`) is the only judge. Parsers, pytest, and citation lookups run before Jev.

Kaggle in the older StormCite plan (`docs/plan-stormcite.md`, superseded but still the original depth):

- A **probe kernel** embeds abstracts with MiniLM, trains logistic regression, writes AUC. Likeness is hidden if holdout AUC is under 0.60. Likeness never becomes an issue by itself.
- A **contrastive kernel** was planned (one epoch, an encoder). It was not what shipped.
- A **claim kernel** generates pytest for a claim that names a dataset slug and runs it on a Kaggle kernel, with an 8-minute timeout and a local fallback labeled `local`.
- The idea people remember as “agents with their own GPU” was: a specialist pushes a kernel, Kaggle runs it on Kaggle’s machines, and the result comes back as `match`, `mismatch`, `missing_row`, or `not_run`. It was not “each agent owns a standing GPU box.”

## What had to be ditched or narrowed

- **The recursive loop is not on the desk.** Playbook routes exist (`POST /runs`, `GET /runs/{id}`, `POST /runs/{id}/replay`, `GET /playbook`). Fitness math is tested. The desk audit does not load patches, does not reread a paper, and stores fitness `1` or `0` instead of the playbook formula.
- **Jev is not the judge on the desk path.** `jev.judge_claim` is real and is called from the older batch pipeline (`services/orchestrator/batches.py`, `_apply_jev`). The desk calls `paper_audit.audit_paper` and then stops. The specialist named `jev` in that file only dedupes findings and writes `jev_label = "contradicted"` on whatever the parsers already found. It does not call OpenRouter.
- **Retrieve does nothing.** The stage exists so the order matches the plan. Its finished line is “No extra sources. The check uses this PDF.”
- **Resolve does not ask whether the cited work exists.** It checks whether `(Author, Year)` or a DOI string appears in the reference section of the same PDF. The Lancet and NeurIPS failures are bibliography entries that look real and match no publication. The desk does not do that catalog check.
- **Support is a word overlap**, not a semantic check and not a Jev judgment. A claim fails support when it shares no word of length 4 or more with the methods and results.
- **Kaggle is two finished kernels plus a narrow rerun, not a GPU agent loop.**
  - Probe: `arxaudit/arxaudit-probe`. Frozen MiniLM (weights from the public dataset `shinomoriaoshi/sentencetransformersallminilml6v2` because the Kaggle Hugging Face client and DNS failed). Logistic regression. Holdout AUC about **0.940** in `kaggle/output/probe/auc.json`. Above 0.60, so likeness may be shown on the old `/audit` screen. The desk does not score likeness.
  - Claim: `arxaudit/arxaudit-claim`. One stored claim on the Titanic CSV: 891 rows, 342 survived. Status `match` in `kaggle/output/claim/results.json`.
  - Desk rerun (`services/orchestrator/repro.py`, kernel `arxaudit/arxaudit-repro`): only if the paper names a public table. Checks `rows`, `sum`, `mean`, or `count_eq`. Does not retrain a model and does not run the paper’s code.
  - Both notebooks are **private**. Publishing returned “Phone verification is required to make a notebook public.”
  - Early probe attempts failed: `sentence-transformers` crashed on a closed Hugging Face client; a raw hub download failed with a DNS error. The working probe does not download the model at runtime.
- **Contrastive training, FAISS retrieval, and citation HTTP resolution** are in the old plan and are not the desk path.
- **No email to authors, no posting verdicts, no fraud label, no “this paper is AI.”** Those are product rules, not missing features.

## What exists and runs

Two programs.

- **Screen.** Next.js 16 App Router at `apps/web`. Chair product is `/desk`. Auth is Supabase (`@supabase/ssr`). The browser never holds `XAI_API_KEY`, `OPENROUTER_API_KEY`, `KAGGLE_KEY`, or the Supabase service role. Next reads `apps/web/.env.local` only.
- **Checker.** FastAPI at `services/orchestrator`, Python 3.12 venv. Local database is gitignored `services/orchestrator/playbook.sqlite`. Do not point `RUN_DB` at `/tmp` if lists should survive a restart. arXiv PDFs cache under `services/orchestrator/.arxiv-cache`.

A chair signs in, creates a conference (a named list), pastes arXiv ids, and runs the queue. New-style ids matching `^\d{4}\.\d{4,5}$` are fetched from `export.arxiv.org`. Two local fixtures are not real papers:

- `0000.00001` Hallucinated Metric Paper, Ada Example. Abstract claims 95.2% and cites Smith, 2099. Results say 61.0%. Only reference is Jones, 2018. Status `contradicted`. Two issues: citation, number. Both on page 1.
- `0000.00002` Measured Metric Paper, Lin Example. Those checks pass.

### The ten specialists, in order

They are a fixed pipeline, not a swarm. Each one writes a one-line event and hands the text to the next. Most are ordinary code.

| Stage | What it actually does |
| --- | --- |
| ingest | Opens the PDF with PyMuPDF and takes the text. |
| sections | Splits on headings: abstract, introduction, methods, results, references. |
| retrieve | No-op. Says the check uses this PDF. |
| extract | Keeps sentences that contain `(Author, Year)`, a DOI, a decimal, or a `owner/dataset` slug. |
| resolve | Citation or DOI missing from the reference section becomes a `citation` issue. |
| numbers | A decimal in the abstract missing from the results becomes a `number` issue. |
| support | Word-overlap failure becomes `support`. A named dataset slug absent from the paper becomes `dataset`. |
| provenance | On the desk, likeness is not scored. The line is “Likeness is not scored on this desk.” |
| kaggle_runner | Looks for a public table. Often “No public table to rerun.” A `mismatch` or `missing_row` becomes a `test` issue. |
| jev | Dedupes issues and stamps `jev_label = contradicted`. Does not call the Jev model. |

An issue is stored as type, claim text, evidence span, label, reason, and page. The page is found by searching the PDF for the span. The screen highlights that same string in the pdf.js text layer. It does not trust a page number from a model.

A paper fails only for citation, number, support, dataset, or a failed rerun. A high AI-likeness score never creates an issue.

### Screen a chair can use

- Sign in, make a list, paste ids, delete a paper, run the queue.
- **Summary** tab: one bar per paper. Result words are Passed, Failed, or Not read. A failed card also names the checks, for example `Failed · Citation, Number`.
- **Chat** on the list. `@` pins a paper. Grok (`grok-4.6`) writes the reply from the stored findings. If the key is missing, a local summary is used. Threads are stored on the conference and survive refresh.
- **Paper page.** PDF in the middle. Specialist column on the right. An agent that found a problem is red and sorted to the top. An agent that finished cleanly is green below it. The agent name is semibold. Clicking an issue marks the sentence in the PDF.
- **Report.** PDF in the middle, findings on the right, each with page and quote. Above the findings, one sentence joined from the stored reasons. Download is still markdown, and that sentence is in the markdown under the verdict. Zip of judged papers. The on-screen report is ahead of `docs/pitch.md`, which still says the report is only markdown and the PDF lives on the paper page.
- Status words on the paper, the report, and the reports index are Passed, Failed, Not read, Waiting, and Running. The database still stores `contradicted`.

Visual system: cream `#f4f0e6`, ink `#1c1915`, rule `#e4dcd0`, gold `#c4a15a`, rust `#8c3a2f`, green `#2f6b4f`. Newsreader titles, IBM Plex Sans body. CSS motion only.

### What is technically real

These parts can be defended in a demo without pretending the harness is running:

- A deterministic audit of a PDF against itself: citation token vs bibliography, abstract number vs results, coarse support, optional public-table count.
- A recorded specialist trace, so a person can see which check spoke.
- A finding that is a quote plus a page in the original PDF, not a score.
- A Kaggle probe with a measured AUC (0.940) that is deliberately not allowed to file an issue.
- One Kaggle claim kernel that reran a public table and matched.
- A playbook implementation that is tested and unwired, with an explicit rule that agents do not edit their own source.
- A Jev client that is tested against the Decisions API and called from the desk verify stage.

## The honesty gap

Jev and the catalog check are on the desk now. `jev.judge_claims` runs on the verify stage. Citation claims go through Crossref, OpenAlex, and Semantic Scholar. Parsers, MiniLM evidence, and catalog lookup still run before Jev.

The gap that remains is table arithmetic and the bounded critic retry. The `tables` stage and the desk `critic()` return immediately; they are not connected. The playbook loop that would re-read a paper after a patch is still unwired. Do not claim the critic re-reads a claim.

If a judge asks “where is the multi-agent recursive harness,” the accurate answer is: the specialist list is the agent trace; the recursion is built beside it and not connected. If they ask “where is Kaggle,” the accurate answer is: two private kernels already ran; the desk rerun is the restricted DSL in `repro.py`, not a GPU agent per paper. If they ask “did you catch the hallucinated citations in the Lancet and NeurIPS papers,” the accurate answer is: the desk can now ask outside catalogs whether a bibliography entry matches a real work, and still catches a number that does not survive the results.

## Constraints that still bind

- Public data only. No private cameras, no 911 or CAD audio, no posting a verdict to X, no emailing authors from the app.
- Do not say fraudulent. Do not say written by AI. Likeness is not an issue.
- Do not commit `.env`. Keys are `XAI_API_KEY`, `OPENROUTER_API_KEY`, `KAGGLE_USERNAME`, `KAGGLE_KEY`, Supabase URL and keys. Never `NEXT_PUBLIC_` for those.
- Confirm-email in Supabase stays on. Do not use the service role to bypass it.
- Agents do not edit their own source to make a run pass.

## Files worth opening

- `docs/pitch.md` — shared description. Stage names and the desk judge match the current read path.
- `docs/plan-orchestrator.md` — the recursive playbook that is not wired to the desk.
- `docs/plan-arxaudit.md` — product plan. `docs/plan-stormcite.md` is superseded.
- `services/orchestrator/paper_audit.py` — the ten stages the desk runs.
- `services/orchestrator/jev.py` — the real Jev client.
- `services/orchestrator/verify.py` — the desk path that calls Jev.
- `services/orchestrator/desk.py` — conferences, chat, markdown report. Calls `audit_paper`.
- `services/orchestrator/repro.py` — the restricted DSL rerun.
- `kaggle/DATASETS.md` — slugs, kernels, and the private-notebook note.
- `apps/web/app/desk/` — the chair screen.
