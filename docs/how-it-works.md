# How ArxAudit works

ArxAudit is a desk for a conference chair. The chair pastes arXiv ids. The desk reads each PDF and returns claims tied to pages. The chair watches the read, asks the list a question, and opens the sentence in the original PDF.

The desk does not call a paper fraudulent or written by AI. A likeness score never becomes a finding.

## The two programs

The screen is a Next.js app. Sign-in is Supabase. An unsigned visit to the desk goes to login. The screen calls the orchestrator, a FastAPI service. Keys for xAI, OpenRouter, and Kaggle stay on that service.

```mermaid
flowchart LR
  chair[Chair]
  web[Next.js desk]
  auth[Supabase]
  api[Orchestrator]
  db[(Desk database)]
  arxiv[arXiv]
  catalogs[Crossref, OpenAlex, Semantic Scholar]
  jev[Jev on OpenRouter]
  grok[Grok]
  kaggle[Public tables]

  chair --> web
  web --> auth
  web --> api
  api --> db
  api --> arxiv
  api --> catalogs
  api --> jev
  api --> grok
  api --> kaggle
```

The desk database holds the list, each paper, its claims, its findings, the specialist trace, and the chat. Accounts live in Supabase. The owner of a list is the signed-in user.

## What the chair does

```mermaid
flowchart TD
  login[Sign in]
  list[Create a list]
  add[Paste arXiv ids or upload a PDF]
  run[Run the list]
  summary[Summary tab: one bar per paper]
  chat[Chat tab: ask the list]
  paper[Open a paper: PDF and findings]
  report[Report and zip]

  login --> list --> add --> run
  run --> summary
  run --> chat
  summary --> paper
  paper --> report
```

Chat and Summary are separate tabs. Chat answers from papers already read. Grok writes that prose and does not decide whether a claim holds. The thread is stored on the list. Summary is one card per paper: the title, a bar through the eleven stages, and the result. A finding jumps the PDF to the page where that sentence was found.

Three local papers are built in so a demo does not need the network:

| Id | Paper | What the read should show |
| --- | --- | --- |
| `0000.00001` | Hallucinated Metric Paper | Abstract says 95.2%. Results say 61.0%. Smith 2099 is missing from the references. |
| `0000.00002` | Measured Metric Paper | 61.0% appears in the abstract and the results. The citation is in the references. |
| `0000.00003` | Adaptive Reasoning Systems | The paper claims a 7.8 point gain. The table is 89.2 minus 84.7, which is 4.5. |

## One paper, eleven stages

Waiting papers are read one after another. Inside a stage, claims of the same kind run four at a time. The stages themselves stay in order.

```mermaid
flowchart TD
  parse[1. Parse the PDF into sections]
  claims[2. Type each claim and record its page]
  evidence[3. Retrieve supporting and contradicting sentences]
  citations[4. Check the bibliography and the catalogs]
  numbers[5. Compare abstract numbers with the results]
  tables[6. Check a claimed gain against the nearest table]
  dataset[7. Note named datasets]
  reproduce[8. Rerun a public table when the paper names one]
  verify[9. Ask Jev to judge the remaining claims]
  critic[10. Widen uncertain evidence, at most three times]
  stamp[11. Collapse duplicates and store the result]

  parse --> claims --> evidence --> citations --> numbers --> tables --> dataset --> reproduce --> verify --> critic --> stamp
```

Each stage writes a started sentence and a finished sentence. The Summary bar follows that trace.

### Parse

The PDF is opened and split into abstract, introduction, related work, methods, results, discussion, and references. The page of a sentence comes from searching the PDF, not from a model.

### Claims

Sentences are typed before any model sees them.

```mermaid
flowchart TD
  sentence[A sentence outside the references]
  citation{Author-year, bracket number, or DOI?}
  comparison{A number plus improves, over, or points?}
  numerical{A decimal or a percent?}
  dataset{A dataset name or a count of rows?}
  semantic{We show, demonstrate, significantly, or robust, and no number?}
  skip[Left as ordinary text]

  sentence --> citation
  citation -->|yes| citationClaim[Citation claim]
  citation -->|no| comparison
  comparison -->|yes| comparisonClaim[Comparison claim]
  comparison -->|no| numerical
  numerical -->|yes| numericalClaim[Numerical claim]
  numerical -->|no| dataset
  dataset -->|yes| datasetClaim[Dataset claim]
  dataset -->|no| semantic
  semantic -->|yes, up to 10| semanticClaim[Semantic claim]
  semantic -->|no| skip
```

Each kept claim gets a stable id from the paper and the sentence, plus the page where the text was found.

### Evidence

Numerical, comparison, and semantic claims get two sets of sentences from the paper. The supporting set is the closest sentences overall. The contradicting set prefers another section that shares a unit, such as percent or accuracy, and states a different number. On the first fixture, the 95.2% claim is paired with the results sentence that says 61.0%.

Embeddings use MiniLM when that model is installed, and a hash embedder otherwise.

### Citations

A citation is checked twice.

```mermaid
flowchart TD
  cite[Citation claim]
  bib{Does the token appear in this paper's references?}
  miss[Issue: cited in the text, missing from the reference list]
  catalogs[Ask Crossref, OpenAlex, and Semantic Scholar]
  strong{DOI match or strong title match?}
  supported[Supported]
  allAnswered{Every catalog answered, and none matched?}
  unresolved[Unresolved]
  weak{One weak match?}
  jevCite[Jev: does this candidate represent the reference?]
  ambiguous[Ambiguous, or supported]
  error[Not checked]

  cite --> bib
  bib -->|no| miss
  bib --> catalogs
  catalogs --> strong
  strong -->|yes| supported
  strong -->|no| allAnswered
  allAnswered -->|yes| unresolved
  allAnswered -->|no| weak
  weak -->|yes| jevCite
  jevCite --> ambiguous
  weak -->|network error and no strong match| error
```

A strong match is an exact DOI, or a title similarity of at least 0.85 with the author or the year within one year. Successful catalog answers are cached. A network failure stays not checked. It is not recorded as unresolved.

### Numbers

An abstract number is compared with the results section. If the results never state that number, the claim is contradicted. If they do, it is supported. Both pages are stored as evidence.

### Tables

A comparison claim is checked against the nearest table. The desk takes the Ours row, subtracts the best other row, and compares that with the claimed gain. The tolerance is 0.05 absolute or 1% relative.

On the demo paper the formula is `89.2 − 84.7 = 4.5`. The claim of 7.8 points is contradicted. That computation is kept, and Jev does not overwrite it.

### Dataset and reproduce

Named datasets are recorded. When a claim names a public table, the desk compiles it into a small allowed calculation: a count, a sum, a mean, or a comparison. A match is reproduced. A disagreeing result is could not reproduce. The desk does not retrain a model and does not run the paper's own code. A dataset sentence with no public table stays not checked.

### Verify

Jev judges numerical, comparison, and semantic claims that do not already have a table computation. The source text is the supporting lines, the contradicting lines, and any number in the claim that does not appear in another section.

```mermaid
flowchart TD
  claim[Eligible claim]
  hasKey{OpenRouter key set?}
  cap{Within the first 40?}
  cache{Cached judgment?}
  jev[Jev: supported, contradicted, or not mentioned]
  network{Call succeeded?}
  store[Store the label and the confidence]
  notChecked[Not checked]

  claim --> hasKey
  hasKey -->|no| notChecked
  hasKey -->|yes| cap
  cap -->|no| notChecked
  cap -->|yes| cache
  cache -->|hit| store
  cache -->|miss| jev
  jev --> network
  network -->|yes| store
  network -->|no| notChecked
```

With no key, the deterministic number check still runs. Jev's answers are cached by the claim text and the source text.

### Critic

This stage runs when a key is set. It looks at claims Jev already judged.

```mermaid
flowchart TD
  judged[Jev judgment]
  uncertain{Not mentioned, or confidence under 0.70?}
  keep[Keep the verdict]
  widen[Widen the evidence window by one or two sentences]
  again[Ask Jev again]
  still{Still uncertain?}
  round{Round 3?}
  human[Insufficient evidence. Requires human review.]

  judged --> uncertain
  uncertain -->|no| keep
  uncertain -->|yes| widen --> again --> still
  still -->|no| keep
  still -->|yes| round
  round -->|no| widen
  round -->|yes| human
```

The claim text is never edited. A patch that would drop a number from the claim is rejected. The steps record "Round 2: widened to ±2 sentences" and the same for round 3.

### Stamp

Duplicate findings collapse. The paper is marked failed if any issue or any finding claim remains. Otherwise it is passed. A paper that could not be opened is not read.

Papers already stored keep the verdicts from the read that produced them. A later read uses the current checks. An old row does not change until that paper is queued again.

## What counts as a finding

```mermaid
flowchart TD
  verdict[Stored verdict]
  hard{Contradicted, unresolved, could not reproduce, or insufficient evidence?}
  semantic{Semantic claim, not mentioned, confidence at least 0.70?}
  finding[Finding]
  shown[Shown, and not a finding]

  verdict --> hard
  hard -->|yes| finding
  hard -->|no| semantic
  semantic -->|yes| finding
  semantic -->|no| shown
```

Ambiguous and not checked are shown. They are not findings.

Screen words follow the stored verdict: Supported, Contradicted, Unresolved, Not found, Reproduced, Could not reproduce, Insufficient evidence, Requires human review, Not checked.

## The scoreboard

The headline counts claims analyzed and claims supported, then any nonzero failure counts. Each category line is passes over every claim of that kind.

| Line | Numerator | Denominator |
| --- | --- | --- |
| Citations resolved | Citation claims marked supported | Every citation claim |
| Internal consistency | Semantic claims marked supported | Every semantic claim |
| Numerical consistency | Numerical and comparison claims marked supported | Every numerical or comparison claim |
| Computational reproduction | Dataset claims marked reproduced | Every dataset claim |

A claim that was not checked stays in the denominator. It does not count as a pass and it does not appear in the failure headline. A line can therefore read `4 / 60`. Computational reproduction stays at zero until a public-table rerun returns reproduced or could not reproduce.

## The report

```mermaid
flowchart TD
  title[Title, id, author, list]
  verdict[Verdict: passed, failed, not read, or not judged yet]
  summary[Summary line]
  categories[Four category lines]
  findings[One section per finding]
  chain[Claim page, evidence page, verdict, confidence, catalog or formula, steps]
  rerun[Rerun]
  trace[Which stages finished]

  title --> verdict --> summary --> categories --> findings --> chain --> rerun --> trace
```

A judged list can be downloaded as a zip of these reports. A paper that has not been run yet says it has not been judged.

## What stays outside the chair's path

The older playbook scores a patch and can reuse it on a later paper. That API is separate. The desk does not load those patches. The recursion a chair can see is the three-round widening inside one paper.

The likeness probe can be measured. Its result stays off the finding list.
