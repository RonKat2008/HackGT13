"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { EXAMPLE_JOB_ID, type ConferenceDesk, type Paper } from "@/lib/desk";
import { categoryLines, failureWhere, findingCount, legendLine, paperLabel, summaryLine, summaryOf } from "@/lib/verdict";
import { AskDesk } from "./[id]/ask";
import { LABELS, ORDER } from "./specialists";

function titleOf(paper: Paper): string {
  return paper.title || paper.arxiv_id;
}

function reach(paper: Paper): number {
  if (paper.status === "passed" || paper.status === "contradicted" || paper.status === "error") {
    return ORDER.length;
  }
  if (paper.status === "running" && paper.specialist) {
    const index = ORDER.indexOf(paper.specialist as (typeof ORDER)[number]);
    if (index >= 0) return index;
  }
  return -1;
}

function resultOf(paper: Paper): { label: string; tone: string } | null {
  if (paper.status === "passed") return { label: paperLabel(paper), tone: "text-[#2f6b4f]" };
  if (paper.status === "contradicted") return { label: paperLabel(paper), tone: "text-[#8c3a2f]" };
  if (paper.status === "error") return { label: paperLabel(paper), tone: "text-[#8c3a2f]" };
  return null;
}

function liveLine(paper: Paper): string {
  const cursor = reach(paper);
  if (paper.status === "running" && cursor >= 0) return `Now · ${LABELS[ORDER[cursor]]}`;
  if (paper.status === "queued") return "Not read";
  const line = summaryLine(summaryOf(paper));
  if (paper.status === "passed") return line || "Every claim checked. Nothing to report.";
  if (paper.status === "contradicted") {
    const count = findingCount(paper);
    return line || (count === 1 ? "1 finding to review." : `${count} findings to review.`);
  }
  if (paper.status === "error") return "The paper could not be read.";
  return "";
}

function keepExample(next: Paper[], current: Paper[]): Paper[] {
  const sample = current.find((paper) => paper.job_id === EXAMPLE_JOB_ID);
  if (!sample || next.some((paper) => paper.job_id === EXAMPLE_JOB_ID)) return next;
  return [sample, ...next];
}

export function DeskViews({
  conferenceId,
  conferenceName,
  initial,
  example = false,
  initialView = "chat",
}: {
  conferenceId: string;
  conferenceName: string;
  initial: Paper[];
  example?: boolean;
  initialView?: "chat" | "summary";
}) {
  const [view, setView] = useState<"chat" | "summary">(example || initialView === "summary" ? "summary" : "chat");
  const [papers, setPapers] = useState(initial);
  const moving = papers.some((paper) => paper.status === "queued" || paper.status === "running");

  useEffect(() => {
    setPapers(initial);
  }, [initial]);

  useEffect(() => {
    if (!moving) return;
    const timer = setInterval(async () => {
      const response = await fetch(`/api/desk/conferences/${conferenceId}`);
      if (!response.ok) return;
      const body = (await response.json()) as ConferenceDesk;
      if (!Array.isArray(body.papers)) return;
      setPapers((current) => (example ? keepExample(body.papers, current) : body.papers));
    }, 800);
    return () => clearInterval(timer);
  }, [conferenceId, moving, example]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div role="tablist" aria-label="Desk view" className="flex shrink-0 items-end gap-1 border-b border-[#e4dcd0] px-4">
        <TabButton id="chat" selected={view === "chat"} onSelect={() => setView("chat")}>
          Chat
        </TabButton>
        <TabButton id="summary" selected={view === "summary"} onSelect={() => setView("summary")}>
          Summary
        </TabButton>
      </div>
      <div
        id="desk-panel-chat"
        role="tabpanel"
        aria-labelledby="desk-tab-chat"
        hidden={view !== "chat"}
        className={view === "chat" ? "flex min-h-0 flex-1 flex-col" : "hidden"}
      >
        <AskDesk conferenceId={conferenceId} conferenceName={conferenceName} papers={papers} />
      </div>
      <div
        id="desk-panel-summary"
        role="tabpanel"
        aria-labelledby="desk-tab-summary"
        hidden={view !== "summary"}
        className={view === "summary" ? "flex min-h-0 flex-1 flex-col" : "hidden"}
      >
        <Summary conferenceId={conferenceId} papers={papers} />
      </div>
    </div>
  );
}

function TabButton({
  id,
  selected,
  onSelect,
  children,
}: {
  id: string;
  selected: boolean;
  onSelect: () => void;
  children: string;
}) {
  return (
    <button
      type="button"
      role="tab"
      id={`desk-tab-${id}`}
      aria-selected={selected}
      aria-controls={`desk-panel-${id}`}
      className={`relative px-4 py-3 text-sm ${selected ? "text-[#1c1915]" : "text-[#6b645c]"}`}
      onClick={onSelect}
    >
      {children}
      <span className={`desk-tabline absolute inset-x-4 bottom-0 h-0.5 bg-[#c4a15a] ${selected ? "scale-x-100" : "scale-x-0"}`} />
    </button>
  );
}

function Summary({ conferenceId, papers }: { conferenceId: string; papers: Paper[] }) {
  return (
    <section aria-label="Paper summary" className="min-h-0 flex-1 overflow-y-auto px-4 py-6 lg:px-8">
      {papers.length === 0 ? (
        <p className="text-sm text-[#6b645c]">No papers on this list yet.</p>
      ) : (
        <ul className="mx-auto flex max-w-3xl flex-col gap-3">
          {papers.map((paper, index) => (
            <li key={paper.job_id} className="desk-rise" style={{ animationDelay: `${index * 40}ms` }}>
              <PaperBar conferenceId={conferenceId} paper={paper} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function PaperBar({ conferenceId, paper }: { conferenceId: string; paper: Paper }) {
  const cursor = reach(paper);
  const running = paper.status === "running";
  const result = resultOf(paper);
  const where = paper.status === "contradicted" ? failureWhere(paper.issues, paper.claims ?? []) : "";
  const [hint, setHint] = useState<string | null>(null);
  const stages = [...ORDER, "result"] as const;
  const categories = categoryLines(summaryOf(paper)).filter((line) => line.total > 0);

  return (
    <article className="rounded-2xl bg-white px-5 py-4 ring-1 ring-[#e4dcd0]">
      <div className="flex items-baseline justify-between gap-4">
        <Link
          href={`/desk/${conferenceId}/${paper.job_id}${paper.job_id === EXAMPLE_JOB_ID ? "?example=1" : ""}`}
          className="line-clamp-2 font-[family-name:var(--desk-serif)] text-2xl leading-tight"
        >
          {titleOf(paper)}
        </Link>
        {result ? (
          <span className={`shrink-0 text-sm ${result.tone}`}>
            {result.label}
            {where ? ` · ${where}` : ""}
          </span>
        ) : null}
      </div>
      <p className="mt-1 text-[11px] tracking-[0.04em] text-[#6b645c]">{paper.arxiv_id}</p>
      <div className="relative mt-4 h-8">
        <div className="pointer-events-none absolute inset-x-0 top-1/2 flex h-2 -translate-y-1/2 overflow-hidden rounded-full bg-[#ebe4d6]" aria-hidden="true">
          {stages.map((name, index) => {
            const now = running && name !== "result" && index === cursor;
            const done = index < cursor;
            return (
              <span
                key={name}
                className={`relative h-full min-w-0 flex-1 ${segmentFill(paper, name, done, now)} ${index > 0 ? "border-l border-white" : ""}`}
              >
                {now ? <span className="desk-sheen" /> : null}
              </span>
            );
          })}
        </div>
        <div className="absolute inset-0 flex">
          {stages.map((name) => {
            const label = name === "result" ? result?.label ?? "Result" : LABELS[name];
            return (
              <Link
                key={name}
                href={`/desk/${conferenceId}/${paper.job_id}?part=${name}${paper.job_id === EXAMPLE_JOB_ID ? "&example=1" : ""}`}
                aria-label={label}
                onMouseEnter={() => setHint(label)}
                onMouseLeave={() => setHint(null)}
                onFocus={() => setHint(label)}
                onBlur={() => setHint(null)}
                className="min-w-0 flex-1 rounded-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#c4a15a]"
              />
            );
          })}
        </div>
      </div>
      <div className="mt-1 flex" aria-hidden="true">
        {stages.map((name, index) => {
          const label = name === "result" ? "Result" : LABELS[name];
          const now = running && name !== "result" && index === cursor;
          return (
            <span
              key={name}
              className={`min-w-0 flex-1 truncate text-center text-[9px] leading-4 ${now ? "text-[#c4a15a]" : "text-[#6b645c]"}`}
            >
              {label}
            </span>
          );
        })}
      </div>
      <p className="mt-2 text-xs text-[#6b645c]">{hint ?? liveLine(paper)}</p>
      {legendLine(summaryOf(paper)) && !running ? (
        <p className="mt-1 text-[11px] leading-5 text-[#6b645c]">{legendLine(summaryOf(paper))}</p>
      ) : null}
      {categories.length > 0 && !running ? (
        <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-[11px] text-[#6b645c] sm:grid-cols-4">
          {categories.map((line) => (
            <div key={line.label} className="flex flex-col">
              <dt className="tracking-[0.04em]">{line.label}</dt>
              <dd className="text-sm text-[#1c1915]">{line.value}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </article>
  );
}

function segmentFill(paper: Paper, name: string, done: boolean, now: boolean): string {
  if (name === "result" && paper.status === "passed") return "bg-[#2f6b4f]";
  if (name === "result" && (paper.status === "contradicted" || paper.status === "error")) return "bg-[#8c3a2f]";
  if (now) return "bg-[#c4a15a]";
  if (done) return "bg-[#1c1915]";
  return "bg-transparent";
}
