"use client";

import { useEffect, useState } from "react";
import type { Paper, Quote } from "@/lib/desk";
import { categoryLines, findingCount, isFinding, paperLabel, summaryLine, summaryOf, verdictTone } from "@/lib/verdict";
import { deletePaper } from "../../actions";
import { AskDesk } from "../ask";
import { MorphLink } from "../../morph-link";
import { evidencePage } from "../../finding";
import { PdfView, type PdfMark } from "../../pdf-view";
import { finishedDetail, issueIndexForPart, issueQuote, orderedClaims, Specialists } from "../../specialists";

const STARTER = `rate = 20 + 22
print("cell result", rate)
`;

export function Workflow({
  conferenceId,
  conferenceName,
  papers,
  initial,
  part = "",
}: {
  conferenceId: string;
  conferenceName: string;
  papers: Paper[];
  initial: Paper;
  part?: string;
}) {
  const [paper, setPaper] = useState(initial);
  const [cells, setCells] = useState([
    {
      id: 1,
      code: initial.kaggle?.code || STARTER,
      output: initial.kaggle?.log || "",
      ok: initial.kaggle?.status !== "mismatch" && initial.kaggle?.status !== "missing_row",
    },
  ]);
  const [busy, setBusy] = useState<number | null>(null);
  const [notebook, setNotebook] = useState(false);
  const [asking, setAsking] = useState(false);
  const [selected, setSelected] = useState(-1);
  const [passage, setPassage] = useState<Quote | null>(null);
  const [claimId, setClaimId] = useState("");
  const [focusPage, setFocusPage] = useState<number | null>(null);
  const [focusToken, setFocusToken] = useState(0);
  const remove = deletePaper.bind(null, conferenceId);
  const unread = !paper.paper_text.trim() && (paper.claims ?? []).length === 0;
  const activeClaim =
    (paper.claims ?? []).find((claim) => claim.claim_id === claimId) ??
    orderedClaims(paper).find((claim) => isFinding(claim)) ??
    orderedClaims(paper)[0];
  const marks: PdfMark[] = activeClaim
    ? [
        { page: activeClaim.page, text: activeClaim.text, role: "claim" },
        ...activeClaim.evidence
          .filter((item) => item.text.trim())
          .map((item) => ({ page: item.page, text: item.text, role: item.role })),
      ]
    : [];

  useEffect(() => {
    const code = paper.kaggle?.code;
    if (!code) return;
    setCells((current) => {
      if (current.length === 1 && current[0].code === STARTER) {
        return [
          {
            id: 1,
            code,
            output: paper.kaggle?.log || "",
            ok: paper.kaggle?.status !== "mismatch" && paper.kaggle?.status !== "missing_row",
          },
        ];
      }
      return current;
    });
  }, [paper.kaggle]);

  useEffect(() => {
    if (paper.status !== "queued" && paper.status !== "running") return;
    const timer = setInterval(async () => {
      const response = await fetch(`/api/desk/papers/${paper.job_id}`);
      if (response.ok) setPaper(await response.json());
    }, 800);
    return () => clearInterval(timer);
  }, [paper.job_id, paper.status]);

  useEffect(() => {
    if (!part) return;
    const index = issueIndexForPart(paper, part);
    const issue = paper.issues[index];
    if (index >= 0 && issue) {
      setSelected(index);
      setPassage(issueQuote(paper, issue, index));
      return;
    }
    setSelected(-1);
    setPassage(null);
  }, [part, paper.job_id, paper.status, paper.issues.length]);

  function selectIssue(index: number) {
    const issue = paper.issues[index];
    if (!issue) return;
    setSelected(index);
    setPassage(issueQuote(paper, issue, index));
  }

  function fromAsk(quote: Quote) {
    if (!quote.text && quote.page == null) {
      setPassage(null);
      setSelected(-1);
      return;
    }
    setPassage(quote);
    const index = paper.issues.findIndex(
      (issue) => issue.evidence_span === quote.text || issue.claim_text === quote.text,
    );
    setSelected(index);
  }

  async function runCell(id: number) {
    const cell = cells.find((item) => item.id === id);
    if (!cell) return;
    setBusy(id);
    const response = await fetch("/api/desk/cells", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: cell.code }),
    });
    const result = (await response.json()) as { output?: string; ok?: boolean };
    setCells((current) =>
      current.map((item) =>
        item.id === id
          ? { ...item, output: result.output ?? "", ok: result.ok !== false }
          : item,
      ),
    );
    setBusy(null);
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="px-6 pt-5 lg:px-8">
        <div className="flex items-center justify-between gap-4">
          <MorphLink href={`/desk/${conferenceId}`} className="shrink-0 text-sm text-[#6b645c]">
            Back to the list
          </MorphLink>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              aria-expanded={asking}
              onClick={() => setAsking((open) => !open)}
              className="rounded-full px-3 py-1.5 text-xs text-[#1c1915] ring-1 ring-[#e4dcd0]"
            >
              Ask
            </button>
            <MorphLink
              href={`/desk/${conferenceId}/${paper.job_id}/report`}
              className="rounded-full px-3 py-1.5 text-xs text-[#1c1915] ring-1 ring-[#e4dcd0]"
            >
              Report
            </MorphLink>
            <form action={remove}>
              <input type="hidden" name="job_id" value={paper.job_id} />
              <input type="hidden" name="open" value="1" />
              <button
                type="submit"
                className="rounded-full px-3 py-1.5 text-xs text-[#1c1915] ring-1 ring-[#e4dcd0]"
              >
                Delete
              </button>
            </form>
            <button
              type="button"
              aria-expanded={notebook}
              onClick={() => setNotebook((open) => !open)}
              className="rounded-full bg-[#1c1915] px-3 py-1.5 text-xs text-[#f4f0e6]"
            >
              Notebook
            </button>
          </div>
        </div>
        <h1 className="mt-4 max-w-3xl font-[family-name:var(--desk-serif)] text-3xl leading-tight">
          {paper.title || paper.arxiv_id}
        </h1>
        <p className="mt-2 text-xs text-[#6b645c]">
          {paper.arxiv_id}
          {paper.author_name ? ` · ${paper.author_name}` : ""}
          {" · "}
          <span className={verdictTone(paper.status)}>{paperLabel(paper)}</span>
        </p>
        <SummaryHeader paper={paper} />
        {part ? <p className="mt-3 max-w-xl text-sm leading-6 text-[#1c1915]">{partNote(paper, part)}</p> : null}
      </header>
      <div className="mt-4 flex min-h-0 flex-1 flex-col lg:flex-row">
        {asking ? (
          <div className="flex min-h-[42vh] w-full min-w-0 flex-col border-b border-[#e4dcd0] lg:min-h-0 lg:w-[min(28rem,38vw)] lg:border-b-0 lg:border-r">
            <AskDesk
              embedded
              conferenceId={conferenceId}
              conferenceName={conferenceName}
              papers={papers}
              onOpenQuote={fromAsk}
            />
          </div>
        ) : null}
        <div
          id="cited-passage"
          role="complementary"
          aria-label="Cited passage"
          className="flex min-h-[50vh] min-w-0 flex-1 flex-col lg:min-h-0"
        >
          {unread && !passage?.text ? (
            <div className="border-b border-[#e4dcd0] px-6 py-4">
              {paper.abstract ? <p className="text-sm leading-6 text-[#1c1915]">{paper.abstract}</p> : null}
              <p className="mt-2 text-sm leading-6 text-[#6b645c]">This paper has not been read yet.</p>
            </div>
          ) : null}
          <div className="min-h-0 flex-1">
            <PdfView
              jobId={paper.job_id}
              page={activeClaim ? null : (passage?.page ?? null)}
              quote={activeClaim ? "" : (passage?.text ?? "")}
              marks={activeClaim ? marks : undefined}
              focusPage={activeClaim ? (focusPage ?? evidencePage(activeClaim)) : (passage?.page ?? null)}
              focusToken={focusToken}
            />
          </div>
        </div>
        <Specialists
          paper={paper}
          selected={selected}
          onSelect={selectIssue}
          focus={part === "result" ? "" : part}
          selectedClaimId={activeClaim?.claim_id ?? ""}
          onSelectClaim={(id) => {
            setClaimId(id);
            const claim = (paper.claims ?? []).find((item) => item.claim_id === id);
            setFocusPage(claim ? evidencePage(claim) : null);
          }}
          onViewEvidence={(page) => {
            setFocusPage(page);
            setFocusToken((token) => token + 1);
          }}
        />
        <aside
          aria-hidden={!notebook}
          className={`desk-notebook shrink-0 overflow-hidden border-[#e4dcd0] ${notebook ? "h-80 w-full border-t lg:h-auto lg:w-80 lg:border-t-0 lg:border-l" : "h-0 w-0 border-0"}`}
        >
          <div className="flex h-full w-full flex-col overflow-y-auto px-4 py-4 lg:w-80">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm">Notebook</h2>
              <button
                type="button"
                className="text-xs underline decoration-[#c4a15a] underline-offset-4"
                onClick={() =>
                  setCells((current) => [
                    ...current,
                    { id: current.length + 1, code: "", output: "", ok: true },
                  ])
                }
              >
                Add cell
              </button>
            </div>
            <ol className="flex flex-col gap-4">
              {cells.map((cell) => (
                <li key={cell.id} className="flex flex-col gap-2">
                  <label className="text-[11px] text-[#6b645c]" htmlFor={`cell-${cell.id}`}>
                    In [{cell.id}]
                  </label>
                  <textarea
                    id={`cell-${cell.id}`}
                    value={cell.code}
                    onChange={(event) =>
                      setCells((current) =>
                        current.map((item) =>
                          item.id === cell.id ? { ...item, code: event.target.value } : item,
                        ),
                      )
                    }
                    rows={4}
                    spellCheck={false}
                    className="bg-[#f7f1e6] px-3 py-2 font-mono text-xs leading-5 outline-none"
                  />
                  <button
                    type="button"
                    onClick={() => runCell(cell.id)}
                    className="w-fit text-xs underline decoration-[#c4a15a] underline-offset-4"
                  >
                    {busy === cell.id ? "Running" : "Run cell"}
                  </button>
                  {cell.output ? (
                    <pre
                      className={`desk-rise overflow-x-auto px-3 py-2 font-mono text-xs ${
                        cell.ok ? "text-[#2f6b4f]" : "text-[#8c3a2f]"
                      }`}
                    >
                      {cell.output}
                    </pre>
                  ) : null}
                </li>
              ))}
            </ol>
          </div>
        </aside>
      </div>
    </div>
  );
}

function SummaryHeader({ paper }: { paper: Paper }) {
  const summary = summaryOf(paper);
  const line = summaryLine(summary);
  if (!line) return null;
  const categories = categoryLines(summary).filter((item) => item.total > 0);
  return (
    <div className="mt-3 max-w-3xl">
      <p className="text-sm leading-6 text-[#1c1915]">{line}</p>
      {categories.length > 0 ? (
        <dl className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-xs text-[#6b645c]">
          {categories.map((item) => (
            <div key={item.label} className="flex items-baseline gap-1.5">
              <dt>{item.label}</dt>
              <dd className="text-[#1c1915]">{item.value}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </div>
  );
}

function partNote(paper: Paper, part: string): string {
  if (part === "result") {
    if (paper.status === "passed") {
      return "Every citation resolved, every number matched, every claim had support, and no rerun failed.";
    }
    if (paper.status === "contradicted") {
      const count = findingCount(paper);
      return count === 1 ? "1 finding to review." : `${count} findings to review.`;
    }
    if (paper.status === "error") {
      return [...paper.events].reverse().find((event) => event.state === "failed")?.detail || "This paper could not be read.";
    }
    return "Not judged yet.";
  }
  return finishedDetail(paper, part) || "This stage has not run yet.";
}
