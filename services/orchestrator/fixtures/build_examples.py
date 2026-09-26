"""Write the four example papers used on the desk.

Run from services/orchestrator:

    .venv/bin/python fixtures/build_examples.py
"""

from __future__ import annotations

from pathlib import Path

from formal import lock, prose, render

HERE = Path(__file__).resolve().parent


def _front(title: str, author: str, affiliation: str) -> list:
    return [
        ("title", title),
        ("authors", author),
        ("affiliation", affiliation),
    ]


def reported() -> list:
    return [
        *_front(
            "Reported Accuracy on a Public Benchmark",
            "Ada Example",
            "Department of Measurement, Example University",
        ),
        ("heading", "Abstract"),
        prose(
            "This note describes how a single accuracy figure was prepared for a public "
            "benchmark release. The work is narrow on purpose. We describe the split, "
            "the scoring script, and the sentence that will be quoted when the figure "
            "is repeated in later writing. The aim is to leave a paper trail from the "
            "abstract claim back to the table that was actually computed."
        ),
        lock("Accuracy reached 95.2% on the public benchmark (Smith, 2099)."),
        prose(
            "Readers who only see the abstract will meet that sentence first. The rest "
            "of the paper says how the split was frozen, which items were excluded, "
            "and where the quoted figure disagrees with the number written beside the "
            "official scoring script."
        ),
        ("heading", "Introduction"),
        prose(
            "Public benchmarks are useful because a later reader can, in principle, "
            "obtain the same items and run the same script. That promise fails quietly "
            "when the number in the abstract is copied from a draft, a slide, or a "
            "different split, and the results section is updated on another afternoon. "
            "The two texts then look equally official."
        ),
        prose(
            "We wrote this paper as a record of one such release. The benchmark itself "
            "is ordinary: a fixed set of items, a frozen answer key, and a script that "
            "counts exact matches. Nothing in the task requires a new model. The "
            "contribution is the written account of which number was computed and "
            "which number was carried into the abstract."
        ),
        prose(
            "The laboratory context is a shared evaluation machine used by several "
            "student projects. Jobs are queued, logs are kept, and the scoring script "
            "is checked into the same directory as the item list. A figure that cannot "
            "be tied to a log line is not ready to quote. We state that rule here "
            "because the abstract of this paper breaks it."
        ),
        prose(
            "Prior notes from this group describe how the item list was cleaned and "
            "how ties in the answer key were resolved. Those notes are cited in the "
            "reference list. This paper does not repeat the cleaning rules. It repeats "
            "only the accuracy sentence, and then places the script output beside it."
        ),
        prose(
            "The audience we have in mind is a reviewer who will not open the log. "
            "That reviewer sees a title, an abstract, and a results paragraph, and "
            "treats them as one measurement. We therefore keep the measurement to a "
            "single script and refuse every summary that would hide a disagreement "
            "between those parts of the paper."
        ),
        prose(
            "Nothing here depends on a private annotator or on a score that cannot "
            "be recomputed from the prediction file. If the prediction file is lost, "
            "the paper should be withdrawn. If the prediction file is replaced, the "
            "abstract has to be rewritten from the new log rather than edited by eye."
        ),
        ("heading", "Methods"),
        prose(
            "The item list was frozen before any score was computed. Each item has one "
            "reference answer. The script reads a prediction file, compares strings "
            "after stripping surrounding space, and writes a single accuracy line to "
            "the log. Partial credit is not awarded. Items with an empty prediction "
            "count as misses."
        ),
        prose(
            "The split used for the quoted figure is the public hold-out. Development "
            "items were used to choose a threshold in an earlier project and are not "
            "part of the number discussed here. We did not retune that threshold for "
            "this release. The prediction file was produced by the system already "
            "described in the group notes, run once, and left unchanged."
        ),
        prose(
            "Two people checked the log. One person confirmed that the prediction file "
            "matched the frozen run. The other person confirmed that the script was "
            "the copy stored with the item list, not a local edit. Neither check "
            "rewrote the abstract. The abstract had already been drafted from an "
            "earlier sheet."
        ),
        prose(
            "The prediction file stores one string per item, in the same order as the "
            "item list. We do not shuffle that order at scoring time. A mismatch in "
            "order would change the accuracy without changing either file's contents, "
            "so the release checklist includes a line count and a spot check of the "
            "first and last identifiers."
        ),
        prose(
            "We considered reporting a confidence interval and decided against it. "
            "An interval would invite a reader to treat the abstract figure and the "
            "script figure as two draws from one distribution. They are not. One of "
            "them is the script. The other was typed into the abstract from a sheet "
            "that predated the script."
        ),
        ("heading", "Results"),
        prose(
            "The scoring script prints one line. That line is the number we treat as "
            "the result of this release. It is not a range and it is not the best of "
            "several runs. The log was copied into the working notes on the same day "
            "the script finished."
        ),
        lock("The model accuracy was 61.0%."),
        prose(
            "The results line above is the script output. It should be the only "
            "accuracy quoted from this release. A reader who compares it with the "
            "abstract will see that the two sentences do not name the same figure. "
            "We leave both sentences in the paper so the disagreement is visible "
            "without consulting the log."
        ),
        prose(
            "No other metric was computed for this note. We did not break the score "
            "down by item type, and we did not compare the system with a second model. "
            "Those comparisons belong in a longer report. Here the only question is "
            "whether the abstract repeats the script."
        ),
        ("heading", "Discussion"),
        prose(
            "The practical lesson is clerical. An abstract drafted before the log is "
            "easy to leave stale, because the sentence sounds finished and the script "
            "output looks like a detail. A reader of the abstract alone cannot see "
            "the substitution. A reader of both sections can."
        ),
        prose(
            "We do not claim that every quoted benchmark figure fails in this way. "
            "We claim only that this release contains both numbers, and that the "
            "reference list does not contain the source named beside the abstract "
            "figure. Checking those two facts requires no model and no new items."
        ),
        prose(
            "A longer version of this note would include the checklist as an appendix. "
            "We omitted it because the checklist is a local convention, not part of "
            "the benchmark. What belongs in the paper is the sentence a reader will "
            "quote and the sentence the script printed."
        ),
        prose(
            "Correspondence about the log can be sent to the author at the department "
            "named above. We will share the prediction file and the script with a "
            "reviewer who asks. We will not replace the abstract figure with the "
            "script figure inside this version. The disagreement is the record."
        ),
        ("heading", "References"),
        ("reference", "Jones, 2018. A real paper about metrics."),
        (
            "reference",
            "Okoro, A. (2018). Cleaning rules for a shared item list. Example Workshop Notes.",
        ),
        (
            "reference",
            "Garcia, L. (2016). How a frozen answer key should be stored. Proceedings of the Example Workshop.",
        ),
    ]


def measured() -> list:
    return [
        *_front(
            "Measured Accuracy on a Public Benchmark",
            "Lin Example",
            "Department of Measurement, Example University",
        ),
        ("heading", "Abstract"),
        prose(
            "This note describes a single public-benchmark score and the citation that "
            "supports the protocol. The abstract and the results section were written "
            "from the same log line. The reference named in the abstract appears in "
            "the reference list. The paper is short because the claim is small."
        ),
        lock("Accuracy reached 61.0% on the public benchmark (Lee, 2020)."),
        prose(
            "The sentence above is the claim a later reader should check. The sections "
            "that follow describe the split, the script, and the log line that the "
            "sentence repeats. No second figure is introduced."
        ),
        ("heading", "Introduction"),
        prose(
            "A measured report is useful when a reader can find the same number in "
            "the place the paper says the number was computed. That standard is easy "
            "to miss once a draft has been revised by several people. We kept this "
            "paper to one score so the check stays obvious."
        ),
        prose(
            "The benchmark is a public item list with a frozen answer key. The "
            "protocol we followed is the one named in the abstract. We did not invent "
            "a new split. We did not average several runs into a number that never "
            "appears in a log. The prediction file comes from one frozen run of the "
            "system already used by this group."
        ),
        prose(
            "The laboratory keeps the scoring script next to the item list. A release "
            "is ready when the abstract, the results section, and the log agree. This "
            "paper is that release. The discussion says what we did not measure, so "
            "a reader does not treat silence as a broader claim."
        ),
        prose(
            "The group has used this benchmark for several earlier class projects. "
            "Those projects are not compared here. Mixing them into one table would "
            "suggest a ranking we did not compute. A reader who wants that ranking "
            "needs every prediction file, not a paragraph that names a winner."
        ),
        prose(
            "We also avoid language that would turn a single log line into a claim "
            "about the task as a whole. The items are one list. The script is one "
            "script. The paper is the note that ties the abstract to that script "
            "and to the protocol entry in the reference list."
        ),
        ("heading", "Methods"),
        prose(
            "Items were scored by exact string match after stripping surrounding space. "
            "Empty predictions count as misses. Partial credit is not used. The "
            "hold-out split is the public one. Development items were not added back "
            "into the score after the threshold had been chosen."
        ),
        prose(
            "The prediction file was produced once and then left alone. Two people "
            "read the log. One confirmed the file name. The other confirmed that the "
            "script was the stored copy. The abstract was edited after that reading, "
            "not before it."
        ),
        prose(
            "We report the accuracy line and nothing else from the script. A confusion "
            "by item type would be a different paper. The method section exists so a "
            "reader can see that the number in the abstract was not taken from a "
            "different split or a different script."
        ),
        prose(
            "Identifiers in the item list are opaque strings. We do not parse them "
            "and we do not drop items whose identifiers look unusual. Dropping items "
            "after seeing the score would make the abstract and the log describe "
            "different sets. The set in this paper is the public hold-out as stored."
        ),
        prose(
            "The reading of the log was done on the shared machine, not from a "
            "screenshot. A screenshot can crop the filename. The checklist asks for "
            "the filename, the line count, and the accuracy line, written out in "
            "the working notes before the abstract is touched."
        ),
        ("heading", "Results"),
        prose(
            "The script wrote one accuracy line. We copy it here in the same wording "
            "the log used, and we use that same figure in the abstract. There is no "
            "second official number in this release."
        ),
        lock("The model accuracy was 61.0%."),
        prose(
            "Because the results line and the abstract name the same figure, a reader "
            "who checks only those two sentences will find them consistent. The "
            "citation in the abstract is the protocol note listed below. We do not "
            "attach the score to any other source."
        ),
        ("heading", "Discussion"),
        prose(
            "The limitation is scope. One frozen run on one public split does not "
            "say how the system behaves on a new item list, and it does not say that "
            "the protocol is the best available. It says that this log and this "
            "abstract match."
        ),
        prose(
            "We would revise the paper if a later run replaced the prediction file. "
            "Until then the sentence in the abstract is the sentence in the results, "
            "and the named protocol is the entry in the reference list."
        ),
        prose(
            "Reviewers who want the prediction file can request it from the author. "
            "The file is not printed here because it is long and because printing "
            "it would not change the sentence that has to match. The sentence is "
            "the accuracy line, repeated once in the abstract and once in the results."
        ),
        ("heading", "References"),
        ("reference", "Lee, 2020. A measured study of public benchmarks."),
        (
            "reference",
            "Okoro, A. (2018). Cleaning rules for a shared item list. Example Workshop Notes.",
        ),
        (
            "reference",
            "Garcia, L. (2016). How a frozen answer key should be stored. Proceedings of the Example Workshop.",
        ),
    ]


def adaptive() -> list:
    return [
        *_front(
            "Adaptive Reasoning Systems",
            "Mira Example",
            "Department of Computer Science, Example University",
        ),
        ("heading", "Abstract"),
        prose(
            "We present an adaptive reasoning system that routes each query through a "
            "learned controller before a reasoning head produces the final answer. "
            "A fixed budget spends the same effort on easy queries and on hard ones. "
            "The controller is meant to spend steps where they change the answer. "
            "This paper states the accuracy we claim, the citations we rely on, and "
            "the public table we use as a counting check."
        ),
        lock("Our model achieves 95.2% accuracy on the held-out benchmark."),
        lock("Our attention layer follows the design introduced by Vaswani et al. (2017)."),
        lock("The controller is a lightweight transformer block (Vaswani et al., 2017)."),
        lock("This result extends the calibration bound of Smith (2099)."),
        lock("The bound is stated for adaptive estimators (Smith, 2099)."),
        ("heading", "Introduction"),
        prose(
            "Reasoning systems are increasingly asked to handle inputs of varying "
            "difficulty. A fixed computation budget wastes effort on easy queries and "
            "starves hard ones. We study a router that allocates reasoning steps per "
            "query and report its effect on accuracy."
        ),
        prose(
            "The router is a small module in front of a reasoning head. It reads the "
            "query, writes a step budget, and stops when the budget is spent or the "
            "head emits an answer. Training updates the router and the head together, "
            "so the budget is not a rule written down after the fact. The question "
            "for a reader is whether the numbers in this paper match the tables and "
            "the public count we name."
        ),
        prose(
            "We keep the task definition narrow. The held-out benchmark is a frozen "
            "item list. The public count is a passenger table with a known size and "
            "a known survival column. Neither check requires the trained weights. "
            "Both checks can be read off the paper and compared with a table."
        ),
        prose(
            "The controller never sees the answer key. It sees the query text and "
            "the step count it has already spent. When the budget is exhausted the "
            "head must answer with whatever state it has. That constraint is what "
            "makes the budget a claim about computation rather than a comment in "
            "the training log."
        ),
        prose(
            "We describe the system in enough detail for a reader to know which "
            "sentences are about the architecture and which sentences are about a "
            "table. The architecture sentences cite earlier work or name a module. "
            "The table sentences name a public file. Mixing those two kinds of "
            "sentence in one paragraph is how a paper becomes hard to check, so "
            "we keep them apart."
        ),
        ("heading", "Related Work"),
        lock(
            "Attention-based sequence models were introduced by (Vaswani et al., 2017) and have "
            "since become the standard backbone for language understanding."
        ),
        lock(
            "Bidirectional pretraining (Devlin et al., 2019) showed that a single pretrained encoder "
            "transfers to many downstream tasks with little task-specific architecture."
        ),
        prose(
            "Adaptive computation has been explored through early-exit classifiers and "
            "mixture-of-experts routing. Our router differs in that it is trained jointly "
            "with the reasoning head rather than fitted afterwards. We do not claim a "
            "new attention variant. We claim a budget module in front of a head whose "
            "block follows the citation above."
        ),
        ("heading", "Methods"),
        lock("We evaluate on the Titanic passenger dataset (Kaggle, yasserh/titanic-dataset)."),
        lock("Of the 891 passengers, 342 survived."),
        lock("317 passengers travelled in first class."),
        prose(
            "Each passenger record is converted to a short textual description and the "
            "system predicts survival from that description. The conversion is a "
            "template, not a learned paraphrase. The point of the table is the count, "
            "which a reader can recompute from the public file without the template."
        ),
        prose(
            "The router and the reasoning head are optimised jointly with a shared "
            "learning rate schedule. We train for at most twenty thousand steps with "
            "a batch of sixty-four and report the mean of three seeds. The schedule "
            "is the same for every seed. We do not pick the best seed after the fact "
            "and present it as the mean."
        ),
        prose(
            "Textual descriptions of each passenger use a fixed template: class, "
            "age when present, and the survival label only at training time. At "
            "test time the label is held out. The template is dull on purpose. A "
            "learned paraphrase would make the count check depend on a second model, "
            "and the count check is supposed to depend only on the file."
        ),
        prose(
            "Seeds are stored with the run directory. A seed that fails to finish "
            "is reported as a failed run, not dropped from the mean. We did not "
            "have a failed seed in the runs described here. The statement is the "
            "rule we would follow if we had."
        ),
        ("heading", "Results"),
        prose(
            "Table two reports accuracy on the held-out benchmark for our method and "
            "two baselines. The baselines use the same head without the router. The "
            "table is the source for the comparison sentence that follows it."
        ),
        ("caption", "Table 2: Accuracy on the held-out benchmark."),
        (
            "table",
            [("Method", "Accuracy"), ("Baseline A", "82.1"), ("Baseline B", "84.7"), ("Ours", "89.2")],
        ),
        lock("Our method improves performance by 7.8 percentage points over the strongest baseline."),
        lock("Our proposed model achieves 61.0% accuracy on the held-out benchmark."),
        lock("Convergence is reached at step 12k for our system and 19k for the baseline."),
        prose(
            "All experiments use the in-distribution split of the benchmark. Latency "
            "measurements were taken on the development server. The ablation below "
            "removes the router and leaves the head in place."
        ),
        ("caption", "Table 3: Ablation of the router."),
        (
            "table",
            [("Configuration", "Accuracy"), ("With router", "89.2"), ("Without router", "83.4")],
        ),
        lock("Removing the router reduces accuracy on the same split, as shown in Table 3."),
        ("heading", "Discussion"),
        lock(
            "Training converges in fewer steps than the baseline because the router is trained jointly."
        ),
        lock("The system is robust to distribution shift across all evaluated domains."),
        lock("Inference latency stays under 40 ms on a single GPU."),
        lock("Removing the router lowers accuracy by more than five points."),
        prose(
            "We leave a study of larger reasoning heads to future work. The claims "
            "above are the ones a reader should be able to point at: a cited bound, "
            "a table comparison, a public count, and a sentence about shift that the "
            "experiments do not actually vary. They are written as sentences so each "
            "one can be checked on its own."
        ),
        prose(
            "The development server used for timing is a single machine shared with "
            "other jobs. A latency sentence from that machine is a sentence about "
            "that machine. It is not a sentence about a deployed service, and it "
            "should not be read as one. We include it because it is the sort of "
            "sentence a paper adds when the main table is already full."
        ),
        prose(
            "Code for the router will be released with the camera-ready version if "
            "the counting checks in this paper are the ones we still stand behind. "
            "Releasing code does not repair a sentence that names the wrong count. "
            "The sentence has to be edited, or the checker will keep failing it."
        ),
        ("heading", "References"),
        (
            "reference",
            "Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., Jones, L., Gomez, A. N., "
            "Kaiser, L., and Polosukhin, I. (2017). Attention is all you need. Advances in "
            "Neural Information Processing Systems. doi:10.48550/arXiv.1706.03762",
        ),
        (
            "reference",
            "Devlin, J., Chang, M.-W., Lee, K., and Toutanova, K. (2019). BERT: Pre-training "
            "of deep bidirectional transformers for language understanding. Proceedings of "
            "NAACL-HLT. doi:10.18653/v1/N19-1423",
        ),
        (
            "reference",
            "Smith, J. (2099). Calibration bounds for adaptive reasoning. Journal of Future Learning, 12(3), 44-61.",
        ),
    ]


def kaggle_table() -> list:
    return [
        *_front(
            "Counting a Public Table",
            "Nia Example",
            "Department of Measurement, Example University",
        ),
        ("heading", "Abstract"),
        prose(
            "This paper makes six statements about one public passenger table and "
            "nothing else. The table is named with the owner and the file used by "
            "readers who download it themselves. Four of the statements repeat counts "
            "and averages that the file supports. Two of them do not. We write both "
            "kinds in the same voice so a reader can see that fluent wording is not "
            "the same thing as a count."
        ),
        prose(
            "No model is trained. No hidden split is used. A later reader who has the "
            "file can recompute every sentence in the methods and results sections "
            "with a spreadsheet. That is the whole experiment."
        ),
        ("heading", "Introduction"),
        prose(
            "Papers often mention a public table and then quote a count from memory. "
            "The count may be from a different export, a filtered view, or a draft "
            "that was never replaced. Because the table is public, the failure is "
            "easy to miss and easy to check. We chose a table whose columns and size "
            "are widely known so the check does not depend on a private extract."
        ),
        prose(
            "The statements below were written to be executable. Each one names a "
            "count, a class, or an average, and each one can be turned into a single "
            "operation on the file. We do not describe a learning system, a prompt, "
            "or a feature pipeline. Those would be a different paper. Here the agent "
            "under test is the counting step."
        ),
        prose(
            "We also include statements we expect to fail. A paper that only repeats "
            "true counts does not show what a checker does when the prose is wrong. "
            "A paper that only repeats false counts does not show a count that "
            "matches. The mix is the demonstration."
        ),
        prose(
            "The passenger list is old, small, and widely mirrored. Those are "
            "features for this paper. A new table with a changing export would "
            "force the sentences to name a date and a checksum. We want the "
            "operation, not the release process, to be the thing a reader watches."
        ),
        prose(
            "Column names in the file are the names we use in the sentences. We do "
            "not rename class to a word, and we do not rename the survival column "
            "to a phrase. A rename would make a correct sentence look wrong to a "
            "checker that trusts the header row, which is the checker we want."
        ),
        ("heading", "Methods"),
        prose(
            "The file is the public passenger list named below. We do not drop any line. "
            "We do not impute a missing age before taking the average. Class is the "
            "integer column already in the file, not a label we invented. Survival "
            "is the integer column already in the file. Fare is the numeric column "
            "already in the file."
        ),
        lock("We evaluate on the Titanic passenger dataset (Kaggle, yasserh/titanic-dataset)."),
        lock("The public table contains 891 passengers."),
        lock("Of the 891 passengers, 342 survived."),
        lock("216 passengers travelled in first class."),
        lock("317 passengers travelled in first class."),
        prose(
            "The two sentences about first class are both in the paper on purpose. "
            "They cannot both match the same column. A reader who believes whichever "
            "sentence appears last will still be wrong about one of them. A reader "
            "who recomputes the column can say which sentence matches."
        ),
        prose(
            "We did not filter to people with a recorded age when stating the "
            "size of the table. The size sentence is about every row. The average "
            "age sentence, in the next section, is about the age column as it is "
            "stored, skipping empty cells the way a spreadsheet average does."
        ),
        ("heading", "Results"),
        prose(
            "The averages below are stated in the same style as the counts. One of "
            "them is the average a spreadsheet returns for the age column. The other "
            "is a fare we wrote because it is a round figure, not because we computed "
            "it. Both sentences name the table."
        ),
        lock("The mean Age is 29.7 on the Titanic table."),
        lock("The mean Fare is 80.0 on the Titanic table."),
        prose(
            "A checker that only reads the prose cannot see the difference. A checker "
            "that opens the file can. We stop at these six statements. Adding a "
            "learned baseline would change the question from whether the count is "
            "true to whether a model is useful, and that is not the question of "
            "this paper."
        ),
        ("heading", "Discussion"),
        prose(
            "Public tables are a good test of a written count because the file "
            "outranks the sentence. The limitation is that a sentence about a "
            "private extract, a trained model, or a plot we did not publish cannot "
            "be checked the same way. We did not write those sentences."
        ),
        prose(
            "If a later export of the same table changes a column name, the sentences "
            "should be revised or the check should fail. Leaving the old sentence "
            "in place is how a paper starts to describe a file it no longer names."
        ),
        prose(
            "We did not contact the publisher of the table, because the table is "
            "already public and the sentences are about its columns. Credit for "
            "the file belongs in the reference list. Credit does not make a wrong "
            "count true."
        ),
        prose(
            "A reviewer can repeat the work with the file and a spreadsheet. Count "
            "every line. Count the survival column. Count the class column. Average "
            "the age column and the fare column. Then read the six sentences again. "
            "The paper is finished when that reading has somewhere to land."
        ),
        ("heading", "References"),
        (
            "reference",
            "Yasser, H. Titanic dataset. Public table, yasserh/titanic-dataset.",
        ),
        (
            "reference",
            "Garcia, L. (2016). How a frozen answer key should be stored. Proceedings of the Example Workshop.",
        ),
    ]


def main() -> None:
    papers = {
        "hallucinated.pdf": ("Example Workshop on Measurement", reported()),
        "human.pdf": ("Example Workshop on Measurement", measured()),
        "demo_paper.pdf": ("Example Workshop on Reasoning", adaptive()),
        "kaggle_paper.pdf": ("Example Workshop on Public Tables", kaggle_table()),
    }
    for name, (head, blocks) in papers.items():
        path = render(HERE / name, head, blocks)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
