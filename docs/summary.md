# ArxAudit

A conference desk that checks the claims in a paper and opens the sentence that did not hold.

HackGT 13. One product: ArxAudit. The chair works at `/desk`.

## The line

Chairs do not have time to re-read every citation, every number, and every table. ArxAudit reads the papers on their list, runs the same checks on each one, and shows the passage that failed. The output is a reason tied to a sentence. It is not a score, and it is not a judgment of the author.

## Why this exists

Published audits show the problem the desk is aimed at. A reference can look correctly formatted and still match no publication. A number in the abstract can disagree with the results. A count of a public table can disagree with the table.

Figures below are from those papers, not from this repo.

- A Lancet audit of about 2.5 million biomedical papers found the rate of references that match no publication rising from about 4 per 10,000 papers in 2023 to 51.3 per 10,000 in late 2025.
- An audit across arXiv, bioRxiv, SSRN, and PubMed Central estimates 146,932 unmatched citations in 2025 (arXiv:2605.07723).
- At ACL venues, papers with at least one unmatched citation went from 20 in 2024 to 281 in 2025. At ML and security venues in 2025, the share of accepted papers with at least two likely unmatched references was about 1.9% at ICLR, 3.4% at ICML, 5.1% at NeurIPS, and 4.8% at USENIX Security (arXiv:2607.00738).

What those studies count is a bibliography entry that does not correspond to a real work. What ArxAudit counts is narrower and checkable: a citation the catalogs cannot match, a number the paper does not support, a claim with no passage behind it, or a public table that does not rerun to the stated figure.

## Who it is for

A conference chair owns a pile of submissions. They need to know which papers have a citation that does not resolve, a number that does not survive the results, or a public-table count that does not match, and they need to see the sentence themselves.

A program committee scans the same list. Summary is for the batch. The paper page is for one submission. Passed means those checks found nothing. A finding means there is a countable problem, each with a passage.

The author is not contacted from the app. A reason is written so a chair could repeat it. The product stops before contact.

## What a chair does

1. Sign in. The list belongs to that account.
2. Create a conference, or open the one already on the desk.
3. Paste arXiv ids, or upload a PDF.
4. Click Run. The papers already on the list move through the reading. The page stays where it is.
5. Open Summary to watch each paper move from Parse through Stamp.
6. Open a paper. The PDF is in the middle. The checks are on the side. Click a finding and the original page opens on that sentence.

Chat is a separate tab. It answers from the stored audit. Run does not open it and does not ask a question.

## What the desk shows

Each paper walks the same eleven stages, in order:

parse, claims, evidence, citations, numbers, tables, dataset, reproduce, verify, critic, stamp.

A finding is one of these:

- **Contradicted.** The paper disagrees with itself, or a table does not support the stated difference.
- **Unresolved.** The catalogs were asked and none of them matched the citation.
- **Could not reproduce.** A named public table was rerun and the number did not match.
- **Insufficient evidence.** The claim was checked and still needs a person.
- **Not mentioned,** for a semantic claim, only when the judge is confident the paper never states it.

A claim that was not checked is not a finding. A likeness score is never a finding. If the likeness probe cannot separate human and generated abstracts (holdout AUC under 0.60), that column stays hidden. The probe we ran is about 0.94, so the score may be shown elsewhere. On this desk it still does not file an issue.

Copy on the desk does not call a paper fraudulent, and it does not say the paper was written by a model.

## What we show on stage

Four example papers. They look like workshop papers. The sentences the audit checks are locked in the text.

| Paper | What the chair should see |
| --- | --- |
| Reported Accuracy on a Public Benchmark | The abstract says 95.2%. The results say 61.0%. The citation Smith, 2099 is not in the reference list as a resolvable work. |
| Measured Accuracy on a Public Benchmark | The abstract and the results both say 61.0%, and the citation resolves inside the paper. This is the clean contrast. |
| Adaptive Reasoning Systems | The same 95.2% against 61.0%. Vaswani et al., 2017 matches a real paper in Crossref. A table claims a 7.8 point gain; the cells give 89.2 − 84.7 = 4.5. Of 891 Titanic passengers, 342 survived, and that count reproduces. The claim that 317 travelled in first class does not: the table has 216. |
| Counting a Public Table | The Kaggle rerun on `yasserh/titanic-dataset`: 891 rows and 342 survived match; 317 first class does not (actual 216); mean Age 29.7 matches; mean Fare 80.0 does not (actual about 32.2). |

Click the finding. The PDF opens on the sentence. The side column names the check and the reason.

## How it is built

Two programs.

**The screen** is a Next.js app in `apps/web`. The chair never holds an API key. Sign-in is Supabase. The list, the PDF, and the specialist column are the product.

**The checker** is a FastAPI service in `services/orchestrator`. It downloads or reads the PDF, runs the eleven stages, and stores the conference, the claims, and the chat in a local database. Keys stay on the server: xAI for prose, OpenRouter for the judge, Kaggle for the public table.

```text
chair  →  Next.js /desk  →  FastAPI
                              │
                              ├─ PyMuPDF          read the PDF
                              ├─ claims           typed sentences, with page and section
                              ├─ MiniLM           passages that support or contradict
                              ├─ catalogs         Crossref, OpenAlex, Semantic Scholar
                              ├─ numbers, tables  abstract vs results, cell arithmetic
                              ├─ reproduce        compile a count, run it on the CSV
                              ├─ Jev              judge a claim against the evidence text
                              └─ critic           one more look, at most three rounds
```

Parsers, citation lookups, and the table rerun run before the judge. The judge does not get to invent a page number. The page comes from searching the PDF, and the highlight is that same string in the text layer.

### The checks

**Claims.** The extractor keeps citations, decimals, comparisons, dataset sentences, and a small set of semantic claims. Each claim has an id, a page, a section, and a type.

**Evidence.** A frozen MiniLM encoder (`all-MiniLM-L6-v2`) indexes the paper and attaches supporting and contradicting passages.

**Citations.** Each citation is asked of Crossref, OpenAlex, and Semantic Scholar. A strong match is supported. No match from a catalog that answered is unresolved. If a catalog errors, the claim stays not checked. That is deliberate: a network failure is not treated as a missing paper.

**Numbers.** A decimal in the abstract that never appears in the results is contradicted, with confidence 1. A later judge that disagrees does not replace that verdict. The step that compared the abstract with the results stays on the claim.

**Tables.** Numerical comparisons are checked against the cells. The demo claim of 7.8 points is contradicted because the table is 89.2 minus 84.7, which is 4.5.

**Reproduce.** Only when the paper names a public table we know. Today that table is the Titanic survival CSV, `yasserh/titanic-dataset`, 891 rows. A claim is compiled into a small set of operations: row count, count equal, sum, mean, median, min, max, percent, difference, percent change. The operation runs in pandas on the downloaded CSV. It does not retrain a model and it does not execute the paper’s code. A match is reproduced. A mismatch is could not reproduce, with the computed value and the claimed value.

**Verify.** Jev (`typesafe/jev-1.13` on the OpenRouter Decisions API) judges a claim against the evidence text. It may answer supported, contradicted, or not mentioned, plus a confidence. Claims that already have a computation are not sent. Claims the number check already contradicted stay contradicted.

**Critic.** If the judge is unsure, or says the claim is not mentioned, a critic may look again, at most three rounds. After that the claim is insufficient evidence and the reason is that it needs a person. The critic does not reopen a number the paper already contradicted.

**Stamp.** Duplicate findings collapse. The reason is one sentence a chair can read.

### Who decides what

Grok writes prose: the chat answer, and a fallback when a dataset sentence does not match a pattern. Grok does not decide whether a claim is true.

Jev is the only model judge. It judges a claim against text it was given. It does not browse, and it does not choose the page.

The rest is code: PDF parsing, catalog HTTP, table arithmetic, and the pandas rerun.

### Likeness, kept off the finding list

A separate probe embeds abstracts with MiniLM and trains logistic regression. Holdout AUC on that run is about 0.940. The rule is unchanged: under 0.60, hide the score. At any AUC, the score does not create an issue. Nearest labeled abstracts, when shown, are context. The label is Human or Generated. It is not a verdict.

### What is built beside the desk

The orchestrator also has a playbook: typed patches (`query_template`, `prompt_rule`, `span_window`), a fitness score, and replay. A patch that lowers fitness is archived. A patch that drops a fact from a claim is blocked. Agents do not edit their own source to make a run pass.

That loop is tested. It is not what a chair runs when they click Run. The specialist list on the paper is the trace they see.

## What we do not do

- We do not label the author, and we do not email them.
- We do not post a result anywhere.
- We do not retrain the paper’s model or run the paper’s own code.
- We do not use private video, emergency-call audio, or dispatch logs.
- We do not treat a likeness score as a reason.

## Stack

| Piece | Where it lives |
| --- | --- |
| Chair screen | Next.js, `apps/web`, route `/desk` |
| Checker | FastAPI, `services/orchestrator` |
| Accounts | Supabase |
| Conference, claims, chat | Local SQLite on the checker |
| PDF text | PyMuPDF |
| Passage search | MiniLM |
| Citation catalogs | Crossref, OpenAlex, Semantic Scholar |
| Judge | Jev on OpenRouter |
| Prose | Grok on xAI |
| Public table | pandas on a Kaggle CSV |

Person A owns the checker: evidence, catalogs, the judge, and the claim contract. Person B owns the screen and the dataset rerun.
