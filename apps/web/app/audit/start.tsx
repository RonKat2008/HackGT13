"use client";

import { FormEvent, useState } from "react";

const SPECIALISTS = [
  "ingest",
  "sections",
  "retrieve",
  "extract",
  "resolve",
  "numbers",
  "support",
  "provenance",
  "kaggle_runner",
  "jev",
] as const;

type Job = {
  job_id: string;
  arxiv_id: string;
  status: string;
  specialist: string;
  issue_count: number;
  title: string;
  authors: string;
};

type Issue = {
  issue_type: string;
  claim_text: string;
  evidence_span: string;
  jev_label: string;
  reason: string;
  arxiv_id: string;
  confidence: number;
};

type Probe = {
  auc: number;
  hidden: boolean;
};

type TestLog = {
  where: string;
  status: string;
  log: string;
  kernel_url: string | null;
  reason: string;
};

type Submission = {
  product: "arxaudit";
  kind: "links" | "batch";
  name: string | null;
  arxiv_ids: string[];
};

type SavedBatch = {
  name: string;
  arxiv_ids: string[];
};

type Selection =
  | { source: "fixture"; arxiv_id: string }
  | { source: "links"; arxiv_id: string }
  | { source: "batch"; index: number; arxiv_id: string };

function parseArxivId(line: string): string | null {
  const trimmed = line.trim();
  if (!trimmed) return null;

  const absMatch = trimmed.match(/\/abs\/([^/?#\s]+)/);
  const pdfMatch = trimmed.match(/\/pdf\/([^/?#\s]+)/);
  let id = absMatch?.[1] ?? pdfMatch?.[1] ?? trimmed;
  id = id.replace(/\.pdf$/i, "");
  return id || null;
}

function parseArxivIds(text: string): string[] {
  const ids: string[] = [];
  for (const line of text.split("\n")) {
    const id = parseArxivId(line);
    if (id) ids.push(id);
  }
  return ids;
}

function defaultIssueArxivId(jobs: Job[], issues: Issue[]): string {
  const fromIssue = issues.find((issue) => issue.arxiv_id)?.arxiv_id;
  if (fromIssue) return fromIssue;
  const withIssue = jobs.find((job) => job.issue_count > 0);
  return withIssue?.arxiv_id ?? jobs[0]?.arxiv_id ?? "";
}

function lastLogLines(log: string, maxLines: number): string {
  const lines = log.replace(/\r\n/g, "\n").split("\n");
  while (lines.length > 0 && lines[lines.length - 1] === "") {
    lines.pop();
  }
  return lines.slice(-maxLines).join("\n");
}

export function AuditStart({
  jobs,
  issues,
  probe,
  testLog,
  datasetUrl,
  kernelUrl,
}: {
  jobs: Job[];
  issues: Issue[];
  probe: Probe;
  testLog: TestLog;
  datasetUrl: string | null;
  kernelUrl: string | null;
}) {
  const defaultId = defaultIssueArxivId(jobs, issues);
  const [mode, setMode] = useState<"links" | "batch">("links");
  const [pasteText, setPasteText] = useState("");
  const [batchName, setBatchName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submission, setSubmission] = useState<Submission | null>(null);
  const [currentReviewIds, setCurrentReviewIds] = useState<string[] | null>(
    null,
  );
  const [batches, setBatches] = useState<SavedBatch[]>([]);
  const [selection, setSelection] = useState<Selection>({
    source: "fixture",
    arxiv_id: defaultId,
  });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    const arxiv_ids = parseArxivIds(pasteText);
    if (arxiv_ids.length === 0) {
      setError("Paste at least one arXiv link or id.");
      return;
    }
    if (arxiv_ids.length > 8) {
      setError("At most 8 papers are allowed.");
      return;
    }

    if (mode === "batch") {
      const name = batchName.trim();
      if (!name) {
        setError("Batch name is required.");
        return;
      }
      const next: Submission = {
        product: "arxaudit",
        kind: "batch",
        name,
        arxiv_ids,
      };
      setSubmission(next);
      setBatches((prev) => [...prev, { name, arxiv_ids }]);
      setSelection({
        source: "batch",
        index: batches.length,
        arxiv_id: arxiv_ids[0],
      });
      return;
    }

    const next: Submission = {
      product: "arxaudit",
      kind: "links",
      name: null,
      arxiv_ids,
    };
    setSubmission(next);
    setCurrentReviewIds(arxiv_ids);
    setSelection({ source: "links", arxiv_id: arxiv_ids[0] });
  }

  let leftHeading = "Papers";
  let leftIds: string[] | null = null;
  let showFixtureJobs = selection.source === "fixture";

  if (selection.source === "links" && currentReviewIds) {
    leftHeading = "This review";
    leftIds = currentReviewIds;
    showFixtureJobs = false;
  } else if (selection.source === "batch") {
    const batch = batches[selection.index];
    if (batch) {
      leftHeading = batch.name;
      leftIds = batch.arxiv_ids;
      showFixtureJobs = false;
    }
  }

  const selectedId = selection.arxiv_id;
  const matchedJob = jobs.find((job) => job.arxiv_id === selectedId);
  const paperTitle = matchedJob?.title ?? selectedId;
  const paperAuthors = matchedJob?.authors ?? null;
  const paperIssue =
    issues.find((issue) => issue.arxiv_id === selectedId) ?? null;
  const runningSpecialist =
    matchedJob?.status === "running" ? matchedJob.specialist : null;
  const logPreview = lastLogLines(testLog.log, 40);

  return (
    <>
      <form
        onSubmit={handleSubmit}
        className="mb-8 flex flex-col gap-4 border border-zinc-200 px-4 py-4"
      >
        <fieldset className="flex flex-wrap gap-4">
          <legend className="mb-2 w-full text-sm font-medium text-zinc-700">
            Mode
          </legend>
          <label className="flex cursor-pointer items-center gap-2 text-sm text-zinc-900">
            <input
              type="radio"
              name="audit-mode"
              value="links"
              checked={mode === "links"}
              onChange={() => setMode("links")}
            />
            Review links
          </label>
          <label className="flex cursor-pointer items-center gap-2 text-sm text-zinc-900">
            <input
              type="radio"
              name="audit-mode"
              value="batch"
              checked={mode === "batch"}
              onChange={() => setMode("batch")}
            />
            Save as batch
          </label>
        </fieldset>

        <div className="flex flex-col gap-1">
          <label
            htmlFor="arxiv-paste"
            className="text-sm font-medium text-zinc-700"
          >
            arXiv links or ids (one per line)
          </label>
          <textarea
            id="arxiv-paste"
            name="arxiv-paste"
            rows={4}
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            className="w-full border border-zinc-300 px-3 py-2 text-sm text-zinc-900"
            placeholder={"2301.07041\nhttps://arxiv.org/abs/2310.06825"}
          />
        </div>

        {mode === "batch" ? (
          <div className="flex flex-col gap-1">
            <label
              htmlFor="batch-name"
              className="text-sm font-medium text-zinc-700"
            >
              Batch name
            </label>
            <input
              id="batch-name"
              name="batch-name"
              type="text"
              required
              value={batchName}
              onChange={(e) => setBatchName(e.target.value)}
              className="w-full border border-zinc-300 px-3 py-2 text-sm text-zinc-900"
            />
          </div>
        ) : null}

        {error ? (
          <p className="text-sm text-red-700" role="alert">
            {error}
          </p>
        ) : null}

        <button
          type="submit"
          className="w-fit border border-zinc-900 bg-zinc-900 px-4 py-2 text-sm font-medium text-white"
        >
          {mode === "links" ? "Review links" : "Save batch"}
        </button>
      </form>

      {batches.length > 0 ? (
        <nav className="mb-8" aria-label="Batches">
          <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-zinc-500">
            Batches
          </h2>
          <ul className="flex flex-col gap-2">
            {batches.map((batch, index) => (
              <li key={`${batch.name}-${index}`}>
                <button
                  type="button"
                  onClick={() =>
                    setSelection({
                      source: "batch",
                      index,
                      arxiv_id: batch.arxiv_ids[0],
                    })
                  }
                  className={`w-full border px-3 py-2 text-left text-sm ${
                    selection.source === "batch" && selection.index === index
                      ? "border-zinc-900 text-zinc-900"
                      : "border-zinc-200 text-zinc-700"
                  }`}
                >
                  {batch.name}
                </button>
              </li>
            ))}
          </ul>
          {currentReviewIds ? (
            <button
              type="button"
              onClick={() =>
                setSelection({
                  source: "links",
                  arxiv_id: currentReviewIds[0],
                })
              }
              className={`mt-2 w-full border px-3 py-2 text-left text-sm ${
                selection.source === "links"
                  ? "border-zinc-900 text-zinc-900"
                  : "border-zinc-200 text-zinc-700"
              }`}
            >
              This review
            </button>
          ) : null}
        </nav>
      ) : null}

      <div className="grid flex-1 gap-6 md:grid-cols-3">
        <section className="flex flex-col gap-4">
          <h2 className="text-sm font-medium tracking-wide text-zinc-500">
            {leftHeading}
          </h2>
          {showFixtureJobs ? (
            <ul className="flex flex-col gap-3">
              {jobs.map((job) => {
                const selected =
                  selection.source === "fixture" &&
                  selection.arxiv_id === job.arxiv_id;
                return (
                  <li key={job.job_id}>
                    <button
                      type="button"
                      onClick={() =>
                        setSelection({
                          source: "fixture",
                          arxiv_id: job.arxiv_id,
                        })
                      }
                      className={`w-full border px-3 py-3 text-left text-sm text-zinc-900 ${
                        selected
                          ? "border-zinc-900 bg-zinc-100"
                          : "border-zinc-200"
                      }`}
                    >
                      <p className="font-medium">{job.arxiv_id}</p>
                      <p className="mt-1 text-zinc-600">Status: {job.status}</p>
                      <p className="text-zinc-600">
                        Specialist: {job.specialist}
                      </p>
                      <p className="text-zinc-600">
                        Issues: {job.issue_count}
                      </p>
                    </button>
                  </li>
                );
              })}
            </ul>
          ) : (
            <ul className="flex flex-col gap-3">
              {(leftIds ?? []).map((id) => {
                const selected = selection.arxiv_id === id;
                return (
                  <li key={id}>
                    <button
                      type="button"
                      onClick={() => {
                        if (selection.source === "batch") {
                          setSelection({
                            source: "batch",
                            index: selection.index,
                            arxiv_id: id,
                          });
                        } else {
                          setSelection({ source: "links", arxiv_id: id });
                        }
                      }}
                      className={`w-full border px-3 py-3 text-left text-sm text-zinc-900 ${
                        selected
                          ? "border-zinc-900 bg-zinc-100"
                          : "border-zinc-200"
                      }`}
                    >
                      <p className="font-medium">{id}</p>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <section className="flex flex-col gap-4">
          <h2 className="text-sm font-medium uppercase tracking-wide text-zinc-500">
            Paper
          </h2>
          <div className="border border-zinc-200 px-3 py-3 text-sm text-zinc-900">
            <p className="font-medium">{paperTitle}</p>
            {paperAuthors ? (
              <p className="mt-1 text-zinc-600">{paperAuthors}</p>
            ) : null}
            <p className="mt-2">
              <a
                href={`https://arxiv.org/abs/${selectedId}`}
                className="text-zinc-900 underline"
                target="_blank"
                rel="noreferrer"
              >
                https://arxiv.org/abs/{selectedId}
              </a>
            </p>
          </div>

          <h2 className="text-sm font-medium uppercase tracking-wide text-zinc-500">
            Issue
          </h2>
          {paperIssue ? (
            <div className="border border-zinc-200 px-3 py-3 text-sm text-zinc-900">
              <p className="font-medium">Type: {paperIssue.issue_type}</p>
              <p className="mt-2">
                <span className="text-zinc-500">Claim: </span>
                {paperIssue.claim_text}
              </p>
              <p className="mt-2">
                <span className="text-zinc-500">Evidence: </span>
                {paperIssue.evidence_span}
              </p>
              <p className="mt-2">
                <span className="text-zinc-500">Jev label: </span>
                {paperIssue.jev_label}
              </p>
              <p className="mt-2">
                <span className="text-zinc-500">Confidence: </span>
                {paperIssue.confidence.toFixed(2)}
              </p>
              <p className="mt-2">
                <span className="text-zinc-500">Reason: </span>
                {paperIssue.reason}
              </p>
            </div>
          ) : (
            <p className="text-sm text-zinc-600">
              No issue for this paper in the fixture.
            </p>
          )}

          {probe.hidden ? (
            <p className="text-sm text-zinc-700">
              Probe below 0.60 AUC on the holdout. AI-likeness hidden.
            </p>
          ) : null}
        </section>

        <section className="flex flex-col gap-4">
          <h2 className="text-sm font-medium uppercase tracking-wide text-zinc-500">
            Trace
          </h2>
          <ol className="flex flex-col gap-2">
            {SPECIALISTS.map((name) => {
              const isRunning = runningSpecialist === name;
              return (
                <li
                  key={name}
                  className={`border px-3 py-2 text-sm ${
                    isRunning
                      ? "border-zinc-900 bg-zinc-100 text-zinc-900"
                      : "border-zinc-200 text-zinc-700"
                  }`}
                >
                  <span className="font-medium">{name}</span>
                  {isRunning ? (
                    <span className="ml-2 text-zinc-600">running</span>
                  ) : null}
                </li>
              );
            })}
          </ol>

          <h2 className="text-sm font-medium uppercase tracking-wide text-zinc-500">
            Test log
          </h2>
          <div className="border border-zinc-200 px-3 py-3 text-sm text-zinc-900">
            <p className="text-zinc-600">where: {testLog.where}</p>
            <pre className="mt-2 overflow-x-auto whitespace-pre-wrap font-mono text-xs text-zinc-800">
              {logPreview}
            </pre>
            {datasetUrl ? (
              <p className="mt-2">
                <a
                  href={datasetUrl}
                  className="underline"
                  target="_blank"
                  rel="noreferrer"
                >
                  Dataset
                </a>
              </p>
            ) : null}
            {kernelUrl ? (
              <p className="mt-1">
                <a
                  href={kernelUrl}
                  className="underline"
                  target="_blank"
                  rel="noreferrer"
                >
                  Kernel
                </a>
              </p>
            ) : null}
            {testLog.kernel_url ? (
              <p className="mt-1">
                <a
                  href={testLog.kernel_url}
                  className="underline"
                  target="_blank"
                  rel="noreferrer"
                >
                  Kernel
                </a>
              </p>
            ) : null}
          </div>
        </section>
      </div>
    </>
  );
}
