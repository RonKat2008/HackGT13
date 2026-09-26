# ArxAudit handoff for Person B

Written 26 Sep 2026. Product is **ArxAudit**, a conference desk that reads research papers. Landfall is not being built. The old name StormCite is retired.

Person A owns the API in `services/orchestrator`. Person B owns the screen in `apps/web` and the Kaggle pull in `kaggle/`. The live screen has moved past the original three-column audit mock. The chair uses `/desk`.

Pushed tip of `main`: `1004ee5` (`feat: show each finding once and a live paper progress bar`). GitHub: https://github.com/RonKat2008/HackGT13/commit/1004ee5

A few changes after that commit are only in the working tree. They are listed under “On this machine, not pushed.”

## On your laptop

Use the Supabase project that already exists. Do not create a second one. The project URL is `https://minsldzdwrtjhnwetczc.supabase.co`. Ask Ronit to add you as a member so you can open the dashboard. Keys are handed over outside git. Never commit them, never paste them into chat, and never prefix them with `NEXT_PUBLIC_`.

### What to install

- Node.js current enough for Next 16, and npm.
- Python 3.12.
- Git.

### Env files

`.env.example` at the repo root lists the names. Two files, both gitignored:

**Repo root `.env`.** The orchestrator reads this. Copy `.env.example` to `.env` and fill:

| Name | Where it comes from | Who uses it |
| --- | --- | --- |
| `SUPABASE_URL` | Supabase → Project Settings → Data API → Project URL | Orchestrator shelf writer |
| `SUPABASE_PUBLISHABLE_KEY` | Supabase → Project Settings → API Keys → publishable key | Kept here too; the browser app reads its own copy |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase → Project Settings → API Keys → secret / service_role | Orchestrator only. Never put this in `apps/web` |
| `XAI_API_KEY` | xAI console | Grok writes the chat reply. Without it, chat uses the local summary |
| `OPENROUTER_API_KEY` | OpenRouter | Jev, the claim judge. Without it, the parsers still run |
| `KAGGLE_USERNAME` | Kaggle → Settings → API | Dataset download and kernel push |
| `KAGGLE_KEY` | The token from that same Kaggle API page | Same |
| `ORCHESTRATOR_URL` | `http://127.0.0.1:8000` | Already in `.env.example` |

`ORGANIZER_EMAIL` and `ORGANIZER_PASSWORD` are a local orchestrator fallback. Make your own desk account instead of sharing that password.

**`apps/web/.env.local`.** Next only loads env files inside `apps/web`. This file is smaller. Put only:

```
SUPABASE_URL=https://minsldzdwrtjhnwetczc.supabase.co
SUPABASE_PUBLISHABLE_KEY=
ORCHESTRATOR_URL=http://127.0.0.1:8000
```

Leave the publishable key value blank in git. Fill it locally. Do not copy the service role into this file. If these three are missing, `/desk` redirects to `/login` and never reaches Supabase.

### Supabase dashboard

1. Open the project above. Confirm you are in that project, not a new one.
2. **Authentication → Sign In / Providers → Email.** Leave the Email provider on. Leave **Confirm email** on. Do not turn it off to get past a stuck signup. If the hour’s mail limit is hit, Ronit confirms the user under **Authentication → Users**.
3. **Authentication → URL Configuration.** Site URL `http://127.0.0.1:3000`. Add redirect URLs `http://127.0.0.1:3000/**` and `http://localhost:3000/**`. Signup sends the confirm link to `{origin}/desk`.
4. **SQL.** `supabase/migrations/001_shelf.sql` is the shelf, probe, and batch tables, plus Realtime on `paper_jobs` and `job_events`. It should already be applied on this project. Do not run it again if those tables exist. The chair’s lists are not stored there.
5. Create your account at `http://127.0.0.1:3000/signup` after the app is running. Password at least 8 characters. If the page says the confirmation was sent and you have no mail, stop and ask Ronit to confirm that user. Then sign in at `/login`.

The first signed-in visit calls `POST /desk/accounts/link` with your Supabase user id (`claims.sub`) and email. That row is what owns conferences on your machine.

### What will not copy over

`services/orchestrator/playbook.sqlite` is gitignored. A fresh clone has no lists, no papers, and no chat. Create a list and paste arXiv ids. Do not set `RUN_DB` to `/tmp` if you want those lists to stay after a restart. The default file is `services/orchestrator/playbook.sqlite`.

`kaggle/downloads/` and `*.joblib` are gitignored. `kaggle/output/probe/auc.json` and `kaggle/output/claim/results.json` are in git. To pull the CSVs again:

```bash
kaggle datasets download -d heleneeriksen/gpt-vs-human-a-corpus-of-research-abstracts -p kaggle/downloads --unzip
kaggle datasets download -d yasserh/titanic-dataset -p kaggle/downloads --unzip
```

The Kaggle CLI reads `KAGGLE_USERNAME` and `KAGGLE_KEY` from the environment, or `~/.kaggle/kaggle.json`. Do not commit that json.

### Start it

From the repo root:

```bash
cd apps/web
npm install
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Install inside `apps/web`. An install at the repo root writes a stray `package.json`. Do not commit that.

In another terminal:

```bash
cd services/orchestrator
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
set -a && source ../../.env && set +a
.venv/bin/uvicorn app:app --app-dir . --host 127.0.0.1 --port 8000
```

`source ../../.env` is from `services/orchestrator`, so the file is the repo-root `.env`. Do not echo that file. Open `http://127.0.0.1:3000`. Health check: `curl -s http://127.0.0.1:8000/health`.

After a Python change, stop the process on port 8000 and start uvicorn again the same way. Next picks up screen edits by itself.

## What a chair can do

Sign in, make a list, paste arXiv ids, and run the list. The desk downloads any new-style id (`2501.01234`). The two local fixtures stay available: `0000.00001` (Ada Example, “Hallucinated Metric Paper”) and `0000.00002` (Lin Example, “Measured Metric Paper”).

Each paper is read by ten specialists, in order:

`ingest`, `sections`, `retrieve`, `extract`, `resolve`, `numbers`, `support`, `provenance`, `kaggle_runner`, `jev`

A paper fails only for a real check: a citation that does not resolve, a number in the abstract missing from the results, a claim with no support in the methods or results, a named dataset that does not resolve, or a public-table rerun that disagrees. A high AI-likeness score never creates an issue. Provenance says “Likeness is not scored on this desk.” Copy never calls a paper fraudulent or AI-written.

The list has two tabs:

- **Chat.** Ask about the papers. Type `@` and a title or id to pin one. The reply plays a short trace (paper chosen, verdict, quote), then the answer. A `[1]` marker opens the cited passage. A gold line runs from that marker toward the gold band on the PDF.
- **Summary.** One card per paper. The name is on the left. One bar walks the stages. The stage that is working is gold. The last slice is the result: Passed, Failed, or Not read. Click a slice to open that part of the paper.

On a paper, the PDF is the stage and the specialists sit on the right. The specialist working now has a gold rule under its name. Click an issue to jump the PDF to that sentence. The page number comes from a search of the PDF. The browser highlights the same string in the rendered text. It does not trust a page number from the model.

Judged papers have a markdown report and a zip of every judged report. Queued and running papers are left out of the zip.

Add papers stores the title and abstract. The left rail shows the name and the arXiv id. The abstract shows on the paper page until the paper has been read. Delete removes a paper from the list.

## What is already built

### Desk screen (`apps/web/app/desk`)

| Piece | Where |
| --- | --- |
| Lists, rail, add, delete, run | `page.tsx`, `rail.tsx`, `add-form.tsx`, `actions.ts` |
| Chat / Summary tabs and the progress bar | `progress.tsx` |
| Chat, trace, markers | `[id]/ask.tsx` |
| Gold line from a marker to the PDF band | `gold-thread.tsx` |
| PDF viewer (pdf.js 4.10.38) | `pdf-view.tsx`, worker at `apps/web/public/pdf.worker.min.mjs` |
| Specialist column and the gold rule | `specialists.tsx` |
| Paper page, including `?part=` from a bar slice | `[id]/[jobId]/page.tsx`, `workflow.tsx` |
| Reports index and one-paper markdown | `[id]/reports/page.tsx`, `[id]/[jobId]/report/` |
| Sign-in wall | `middleware.ts` sends unsigned `/desk` to `/login` |

Auth is Supabase through `@supabase/ssr`. The owner id is `claims.sub`. Project URL: `https://minsldzdwrtjhnwetczc.supabase.co`. Keys stay server-side. Never `NEXT_PUBLIC_` for `XAI_API_KEY`, `OPENROUTER_API_KEY`, `KAGGLE_USERNAME`, `KAGGLE_KEY`, `SUPABASE_URL`, or `SUPABASE_SERVICE_ROLE_KEY`.

Visual system: cream `#f4f0e6`, ink `#1c1915`, rule `#e4dcd0`, gold `#c4a15a`, rust `#8c3a2f`, green `#2f6b4f`. Newsreader for titles, IBM Plex Sans for the rest. Motion is CSS only (`desk-rise`, `desk-pulse`, `desk-rule`, `desk-sheen`, `desk-tabline`). No framer-motion. `prefers-reduced-motion` turns the motion off.

The public home is `apps/web/app/(site)/`. The older audit mock is still at `apps/web/app/audit`. The chair-facing product is `/desk`.

### API (`services/orchestrator`)

Local desk database: `services/orchestrator/playbook.sqlite` (gitignored). Tests set `RUN_DB` themselves.

Useful desk routes:

- `GET /desk/conferences/{id}`
- `POST /desk/conferences/{id}/submissions`
- `DELETE /desk/conferences/{id}/papers/{job_id}`
- `POST /desk/conferences/{id}/run`
- `GET /desk/papers/{job_id}`
- `GET /desk/papers/{job_id}/pdf`
- `POST /desk/conferences/{id}/ask`
- `GET /desk/papers/{job_id}/report`
- `GET /desk/conferences/{id}/reports.zip`
- `POST /desk/cells` (one notebook cell, local Python)

Next proxies these under `apps/web/app/api/desk/` and requires a signed-in desk user.

Repeated findings are collapsed. The key is issue type plus the evidence span (or the reason if the span is empty). The same support blob that was stored 118 times is served once, with a reason that says how many claims shared it. Collapse happens when the paper is judged and again when an old paper is read. Chat is also told to mention each finding once.

Any arXiv id matching `^\d{4}\.\d{4,5}$` is fetched from `export.arxiv.org`, cached under `services/orchestrator/.arxiv-cache`, and checked for a `%PDF` header. Titles and abstracts are stored at add time. The batch API still caps a single paste at 8 ids. The desk paste does not.

### Kaggle (Person B’s lane, already pulled)

Recorded in `kaggle/DATASETS.md`.

- Abstracts: `heleneeriksen/gpt-vs-human-a-corpus-of-research-abstracts`. Labels `ai_generated` and `is_ai_generated`. File `kaggle/downloads/data_set.csv`.
- Tabular rerun: `yasserh/titanic-dataset`. Target `Survived`. File `kaggle/downloads/Titanic-Dataset.csv`.
- Probe kernel: https://www.kaggle.com/code/arxaudit/arxaudit-probe. Holdout AUC in `kaggle/output/probe/auc.json` is about `0.940`. That is above `0.60`, so likeness may be shown where the old audit screen still has that column. The desk does not score likeness.
- Claim kernel: https://www.kaggle.com/code/arxaudit/arxaudit-claim. `kaggle/output/claim/results.json` is `where: kaggle`, `status: match`.

Both notebooks are private until the Kaggle account verifies a phone number.

The desk rerun is narrower than a full paper reproduction. If a claim or the methods, results, or abstract names a public Kaggle slug (or the text says kaggle and titanic), the worker checks `rows`, `sum`, `mean`, or `count_eq` on that CSV. It does not retrain a model and it does not run arbitrary paper code. Kernel id: `arxaudit/arxaudit-repro`.

### Playbook (exists, not yet wired into a paper read)

`POST /runs`, `GET /runs/{id}`, `POST /runs/{id}/replay`, and `GET /playbook` implement the shared loop. A patch is one of `query_template`, `prompt_rule`, or `span_window`. Fitness decides live versus archived. A patch that drops a fact from a claim is blocked. Agents do not edit their own source to make a run pass.

The desk audit does not load those patches yet. A judged paper stores fitness `1` when it passed and `0` when it failed. That number is not the playbook formula.

## On this machine, not pushed

These files differ from `1004ee5`:

- Chat history. `desk_messages` stores each question and reply for a conference, including the trace, quotes, and cited ids. `GET /desk/conferences/{id}/messages` returns them. The chat loads that list on open, so a refresh keeps the thread. Covered by `test_ask_uses_the_mentioned_paper`.
- The “Nearest reference abstracts. This is not a verdict.” block is removed from the paper page. It is still on the old audit screen (`apps/web/app/audit/start.tsx`) and in the home film (`apps/web/app/(site)/films.tsx`). The generated markdown report no longer includes that section.
- Root `package.json` and `package-lock.json` are an accidental install. Web dependencies live in `apps/web`. Do not commit the root files.

The orchestrator has to be restarted to pick up Python changes. From `services/orchestrator`, source the root `.env` without printing it, then run uvicorn on `127.0.0.1:8000`. Next runs from `apps/web` on `127.0.0.1:3000`.

## Still planned

1. **Reports.** The report should read as a document, with each finding citing a page and a quote from the original PDF. The PDF should sit on the right of that report so a click opens the passage. Download can stay markdown, and a neat PDF export is optional. This is not built yet. Today the report page is rendered markdown, and the paper page is where the PDF lives.
2. **Playbook on the desk.** When a citation, number, support check, or rerun fails, the critic may propose one draft patch for the specialist that missed or over-fired. The same paper is read again, at most three rounds. Jev scores the new read. Fitness is `0.5` faithful + `0.3` resolved + `0.2` cheaper − `0.6` if the patch gamed the result. A rise promotes the patch to live. A fall archives it. The next paper loads the five best live `arxaudit` patches before the first specialist. `POST /runs/{id}/replay` is the same idea for one PDF. A patch that makes a finding vanish by deleting the citation, number, or claim is archived by the retry guard.
3. **Chat as memory for that loop.** Saved threads are the record of what the chair asked and what the desk claimed. A later patch should be able to point at that thread. Do not train on the chair’s mail, and do not store secrets in the message rows.
4. **Finish removing the shelf line** from the home film and the old audit screen, since the desk no longer shows it.
5. **Confirm-email** for Supabase signup stays a dashboard setting. Do not hunt access tokens or use the service role to bypass it.

## Rules that still bind the screen

- Public data only. No private cameras, no 911 or CAD audio, no posting a verdict to X.
- Issues come from failed citations, failed number checks, low claim-to-evidence similarity, or a failed rerun. Likeness alone is not an issue.
- If a probe AUC on the Kaggle holdout is under `0.60`, hide AI-likeness. The current probe is about `0.94`.
- Shelf labels, where they still appear, are Human or Generated.
- Do not commit `.env`. Do not print keys.

## How to run a check

Orchestrator tests, from `services/orchestrator` with the venv (pytest needs to see the venv, so a sandbox that hides it will fail):

```bash
.venv/bin/python -m pytest tests/test_desk.py tests/test_paper_audit.py -q
```

Web types, from `apps/web`:

```bash
node node_modules/typescript/bin/tsc --noEmit
```

Use that `tsc`. `npx tsc` installs the wrong package.
