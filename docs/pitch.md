# ArxAudit

A quiet desk for the papers a conference chair is responsible for.

HackGT 13. The product is ArxAudit. Landfall is out of scope. The old name StormCite is retired. This is not a hurricane tool and it is not a detector that declares a paper fraudulent or written by AI.

## The idea

A chair pastes arXiv ids. The desk reads each PDF and keeps a list of concrete problems: a citation that does not resolve, a number in the abstract that never appears in the results, a claim with no support in the methods or results, a named dataset that does not resolve, or a public table rerun that disagrees with the paper. The chair can ask the list a question, watch each paper move through the reading, and open the sentence that failed inside the original PDF.

The point is a second pair of eyes on the claims a chair would otherwise have to check by hand. The output is a reason tied to a passage, not a score and not a verdict.

## Pitch

**One sentence.** ArxAudit is the desk a conference chair uses to check the claims in the papers they are responsible for, and to open the exact sentence that failed.

**Thirty seconds.** Chairs do not have time to re-read every citation and every number. ArxAudit takes a list of arXiv papers and walks each one through the same checks: does the citation exist, does the abstract’s number show up in the results, does the claim have support, and does a named public table rerun. Chat answers from that audit. Summary shows each paper moving through the stages and landing on Passed or Failed. Click a finding and the original PDF opens on that passage. A likeness score never becomes the reason.

**What we do not say.** We do not say a paper is fraudulent. We do not say it was written by AI. We do not post a verdict anywhere. A high likeness score is not an issue. If the likeness probe cannot separate human and generated abstracts well enough, that column stays hidden.

## Scope

**In.**

- One chair, one list of papers, any new-style arXiv id, plus the two local fixtures used to demo a failed paper and a clean one.
- Ten reading stages, from opening the PDF to stamping the problems.
- A chat that stays on the list, and a summary that shows progress and a result.
- The original PDF beside the finding, with the failed sentence marked.
- A markdown report per judged paper, and a zip of those reports.
- A bounded rerun when the paper names a public table.
- An account per chair, so the list belongs to them.

**Out.**

- Landfall, storms, maps, and generated storm footage.
- Private cameras, 911 audio, or CAD calls.
- Emailing authors from the app, SMTP, or posting to X.
- Retraining the paper’s model or running the paper’s own code.
- Treating student essays or a synthetic abstracts dump as the reference shelf.
- Rewriting the auditor’s source code so a run looks better. Improvement, when it lands, is a scored playbook of small patches.

**Who builds it.** Person A owns the API. Person B owns the screen and the Kaggle pull. The chair-facing app is `/desk`.

## Goals

1. A chair can paste papers they actually have, not only two demo PDFs, and get a reading back.
2. The same finding is shown once. Repeating the same citation or the same unsupported claim is a bug.
3. The chair can see where each paper is, and a result at the end, without losing the chat.
4. Every finding can be opened in the original paper.
5. The reason is something a chair can use: one sentence, tied to evidence.
6. Later, a failed check can teach the next paper how to look, and only if that change holds up under a second read.

The first five are in the desk now. The sixth is designed and not yet wired into a paper read. Saved chat is the memory that later loop can point at.

## Audience

**The chair.** They are responsible for a pile of submissions. They need to know which papers have a broken citation or a number that does not survive the results section, and they need to see it themselves. They are not asking for a fraud label they would have to defend. They ask “what failed on this paper?” and they expect the sentence.

**The program committee.** They inherit the same list. The summary is for scanning a batch. The report is for taking one paper away. Passed means those checks found nothing. Failed means there is a countable set of problems, each with a passage.

**The author, indirectly.** The desk does not email them and does not store a mail password. A reason is written so a chair could repeat it. The product stops before contact.

**The demo audience at HackGT.** They should see one list, one paper that fails for a real citation, one paper that does not, the PDF with the sentence marked, and the bar moving while a paper is still being read. They should also hear the limit: this is an audit of claims against the paper and against public data, not a judgment of the author.

**The two people building it.** Person A lives in the orchestrator and the checks. Person B lives in the screen and the datasets the checks rerun. The pitch above is the shared description. The handoff for setup is `docs/handoff-person-b.md`.

## Feature depth

**Shipped.**

- Sign in, create a list, paste arXiv ids, store the title and abstract, delete a paper.
- Run the queue. Specialists report one sentence each: opened the PDF, found the sections, pulled claims, citations that do not resolve, numbers missing from results, claims without support, no likeness score, a rerun or “no public table,” and a stamp of the problems.
- Chat with `@` mentions, a trace of what was chosen, and numbered markers into the PDF. A gold line connects the marker to the highlighted band.
- Summary as its own tab: one bar per paper, the live stage in gold, the result at the end. Click a stage to open that part of the paper.
- Duplicate findings collapse. A paper that stored the same support problem many times is shown once.
- Markdown report and a zip of judged papers. Chat history is stored on the conference so a refresh keeps the thread.
- Fixture pair: `0000.00001` fails, `0000.00002` is the clean contrast.

**Designed, not the chair’s main path yet.**

- The report as a document on the left and the PDF on the right, each finding citing its page. Today the report is markdown and the PDF lives on the paper page.
- The playbook. A failed check may propose one small patch to how the next read searches or how wide a span it uses. The same paper is read again. If the read gets more faithful, the patch stays. If it gets worse, or if it only passed by dropping the fact, the patch is archived. The next paper loads the few patches that have earned it. Agents do not edit their own code to force a pass.
- Nearest labeled abstracts as context. Labels are Human or Generated. That block was removed from the paper page because it was being read as a verdict. It is not one.

**Explicitly not a feature.** Reject buttons, fraud stamps, “this paper is AI,” and likeness as a reason to write the author.

## Technical depth

**Read path.** A new-style arXiv id is downloaded, cached, and checked for a PDF header. Text is split into sections. Specialists run in order: ingest, sections, retrieve, extract, resolve, numbers, support, provenance, a table rerun, then a stamp. Parsers and citation lookup run before any model judgment. Grok writes prose for the chat. Jev, through OpenRouter, judges a claim against evidence text. The browser never trusts a page number from the model. The page comes from searching the PDF. The highlight is the same string found in the rendered text layer.

**What counts as an issue.** Citation, number, support, dataset, or a failed rerun. Provenance does not open an issue. If the abstract-corpus probe’s holdout AUC is under 0.60, likeness is hidden. The probe that was run sits above that line. The desk still does not turn likeness into a finding.

**Rerun.** Only when the paper names a public table. The worker checks rows, a sum, a mean, or a count. It does not retrain a model and it does not execute the paper’s code. The datasets in use are a public corpus of human and GPT research abstracts, and the Titanic survival table for a claim that names that table.

**Memory.** Conference lists, issues, specialist events, and chat turns live in the local desk database. Accounts are Supabase. The owner of a list is the signed-in user id. Keys stay on the server.

**Learning, when it is connected.** Patches are typed: a query template, a short prompt rule, or a wider sentence window. Fitness is mostly “were the findings faithful,” then “did the check resolve,” then “was the read cheaper,” with a heavy penalty if the patch gamed the result. Live patches are reused. Archived patches are not. Replay is the same paper with the updated playbook.

**Screen.** Next.js. The list is Chat or Summary, not both at once. Summary is one card and one bar. The paper page is the PDF plus the specialist column. Motion is a short set of CSS transitions. The type is a serif for titles and a plain sans for the rest. The palette is cream, ink, and a single gold for the thing that is happening now.

## The line to remember

ArxAudit helps a chair find the sentence that does not hold. It does not decide what the author is.
