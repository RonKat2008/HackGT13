"use client";

import { useEffect, useState } from "react";
import type { Issue, Paper } from "@/lib/desk";

const ORDER = [
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

const LABELS: Record<string, string> = {
  ingest: "Ingest",
  sections: "Sections",
  retrieve: "Retrieve",
  extract: "Extract",
  resolve: "Resolve",
  numbers: "Numbers",
  support: "Support",
  provenance: "Provenance",
  kaggle_runner: "Rerun",
  jev: "Stamp",
};

function finishedDetail(paper: Paper, name: string): string {
  const event = [...paper.events]
    .reverse()
    .find((item) => item.specialist === name && item.state === "finished");
  if (!event || !event.detail || event.detail === name) return "";
  return event.detail;
}

function cardState(paper: Paper, name: string): "idle" | "now" | "done" {
  if (paper.status === "running" && paper.specialist === name) return "now";
  if (finishedDetail(paper, name) || paper.events.some((event) => event.specialist === name && event.state === "finished")) {
    return "done";
  }
  if (paper.status === "passed" || paper.status === "contradicted") return "done";
  return "idle";
}

export function Specialists({
  paper,
  selected,
  onSelect,
}: {
  paper: Paper;
  selected: number;
  onSelect: (index: number) => void;
}) {
  const [announcement, setAnnouncement] = useState("");
  const finished = paper.events.filter((event) => event.state === "finished").length;

  useEffect(() => {
    const event = [...paper.events].reverse().find((item) => item.state === "finished");
    if (!event) return;
    const sentence = event.detail && event.detail !== event.specialist ? event.detail : "";
    setAnnouncement(`${LABELS[event.specialist] ?? event.specialist} finished. ${sentence}`.trim());
  }, [finished, paper.events]);

  const failed = [...paper.events].reverse().find((event) => event.state === "failed");

  return (
    <aside className="flex h-full min-h-0 w-full flex-col overflow-y-auto border-[#e4dcd0] bg-[#f7f3ea] px-4 py-4 lg:w-72 lg:border-l">
      <p className="text-[11px] tracking-[0.16em] text-[#6b645c]">SPECIALISTS</p>
      <p className="sr-only" aria-live="polite">
        {announcement}
      </p>
      <ol className="mt-4 flex flex-col gap-3">
        {ORDER.map((name) => {
          const state = cardState(paper, name);
          const sentence = finishedDetail(paper, name);
          return (
            <li
              key={name}
              className={state === "done" ? "desk-rise" : ""}
            >
              <p className="text-sm text-[#1c1915]">{LABELS[name]}</p>
              {state === "now" ? (
                <p className="mt-1 flex items-center gap-2 text-xs text-[#8a6a2f]">
                  <span className="desk-pulse inline-block size-1.5 rounded-full bg-[#c4a15a]" />
                  now
                </p>
              ) : null}
              {state === "done" && sentence ? (
                <p className="mt-1 text-xs leading-5 text-[#6b645c]">{sentence}</p>
              ) : null}
            </li>
          );
        })}
      </ol>
      <div className="mt-6 border-t border-[#e4dcd0] pt-4">
        {paper.status === "passed" && paper.issues.length === 0 ? (
          <p className="text-sm leading-6 text-[#1c1915]">
            No fabricated citation, missing number, unsupported claim, or failed rerun.
          </p>
        ) : null}
        {paper.status === "error" ? (
          <p className="text-sm leading-6 text-[#8c3a2f]">
            {failed?.detail || "This paper could not be read."}
          </p>
        ) : null}
        {paper.issues.length > 0 ? (
          <ul className="flex flex-col gap-2">
            {paper.issues.map((issue, index) => (
              <li key={`${issue.issue_type}-${index}`}>
                <button
                  type="button"
                  onClick={() => onSelect(index)}
                  className={`w-full rounded-2xl px-3 py-3 text-left ring-1 ${
                    index === selected ? "bg-white ring-[#c4a15a]" : "bg-transparent ring-[#e4dcd0]"
                  }`}
                >
                  <span className="text-[11px] tracking-[0.12em] text-[#8a6a2f]">{issue.issue_type}</span>
                  <span className="mt-1 block text-sm leading-5 text-[#1c1915]">{issue.reason}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </aside>
  );
}

export function issueQuote(paper: Paper, issue: Issue, index: number) {
  return {
    quote_id: `${paper.job_id}-${index}`,
    job_id: paper.job_id,
    arxiv_id: paper.arxiv_id,
    title: paper.title || paper.arxiv_id,
    page: typeof issue.page === "number" ? issue.page : null,
    text: issue.evidence_span || issue.claim_text,
    issue_type: issue.issue_type,
    reason: issue.reason,
  };
}
