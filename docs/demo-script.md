# Demo script

One list, already signed in. The list name on screen is Sohaib. Do not create a conference. Do not open a signup form.

## Clicks

1. Open `/login` and sign in. The desk opens the one list.
2. The rail lists three papers. Leave all of them. Do not press Delete.
3. Click **Adaptive Reasoning Systems**. The PDF is the paper. The column beside it is the findings.
4. Click the 95.2 finding. The PDF marks that sentence.
5. Click the 7.8 finding, then the 317 finding.
6. Go back to the rail and click **Reported Accuracy on a Public Benchmark** (`0000.00001`). It is the paper that fails.
7. Click **Measured Accuracy on a Public Benchmark** (`0000.00002`). The rail says Verified.
8. If someone asks for the written reasons, open **Reports**.

Run is already finished. Press Run only if a paper still says Waiting.

## What to point at

**Adaptive Reasoning Systems**

- “Our model achieves 95.2% accuracy…” is Contradicted. The number check did it. 95.2 is in the abstract and absent from the results. Lya did not make that call.
- “improves performance by 7.8 percentage points…” is Contradicted. The table is 89.2 − 84.7 = 4.5.
- “342 survived” is Reproduced. The public Titanic table count is 342.
- “317 passengers travelled in first class” is Could not reproduce. The same table count is 216.
- “Training converges… because the router is trained jointly” is Contradicted by Lya, at 0.96. Say the model stored that. Do not argue it into Supported.
- “Robust to distribution shift” and “lowers accuracy by more than five points” went to Jev and ended Requires human review.

**The pair**

- `0000.00001` is Contradicted. The abstract says 95.2 and the results say 61.0. The report also says Smith, 2099 does not appear in the references.
- `0000.00002` is Verified. Nothing to report. 61.0 is in the abstract and the results.

## How the judge works

Say this, in this order.

A number check, a table formula, or a finished rerun is stored before either model. Lya then reads the claim and the evidence rows. If Lya’s confidence is at least 0.90, that verdict is the one on the card. Jev runs only when Lya is not sure. Jev may ask for at most two lookups, for at most three rounds. If it is still unsure, the card says Requires human review.

A catalog that errors stays Not checked. It does not become Unresolved. Unresolved is only when Crossref, OpenAlex, and Semantic Scholar all answer and none match.

Likeness is never a finding.

## Lines never to say

- fraudulent, fraud
- fake
- fabricated
- AI-written, written by AI, model-written
- the paper failed because it sounds like a model

Say “the citation is missing from the references,” “the number is absent from the results,” “the table computes 4.5,” “the public count is 216,” or “this claim needs a person.”
