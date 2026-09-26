"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { ConferenceDesk, Paper } from "@/lib/desk";
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
  if (paper.status === "passed") return { label: "Passed", tone: "text-[#2f6b4f]" };
  if (paper.status === "contradicted") return { label: "Failed", tone: "text-[#8c3a2f]" };
  if (paper.status === "error") return { label: "Not read", tone: "text-[#8c3a2f]" };
  return null;
}

function liveLine(paper: Paper): string {
  const cursor = reach(paper);
  if (paper.status === "running" && cursor >= 0) return `Now · ${LABELS[ORDER[cursor]]}`;
  if (paper.status === "queued") return "Waiting";
  if (paper.status === "passed") return "Every stage finished.";
  if (paper.status === "contradicted") return "Stopped on a failed check.";
  if (paper.status === "error") return "The paper could not be read.";
  return "";
}

export function DeskViews({
  conferenceId,
  conferenceName,
  initial,
}: {
  conferenceId: string;
  conferenceName: string;
  initial: Paper[];
}) {
  const [view, setView] = useState<"chat" | "summary">("chat");
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
      if (Array.isArray(body.papers)) setPapers(body.papers);
    }, 800);
    return () => clearInterval(timer);
  }, [conferenceId, moving]);

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
  const [hint, setHint] = useState<string | null>(null);
  const stages = [...ORDER, "result"] as const;

  return (
    <article className="rounded-2xl bg-white px-5 py-4 ring-1 ring-[#e4dcd0]">
      <div className="flex items-baseline justify-between gap-4">
        <Link
          href={`/desk/${conferenceId}/${paper.job_id}`}
          className="line-clamp-2 font-[family-name:var(--desk-serif)] text-2xl leading-tight"
        >
          {titleOf(paper)}
        </Link>
        {result ? <span className={`shrink-0 text-sm ${result.tone}`}>{result.label}</span> : null}
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
                href={`/desk/${conferenceId}/${paper.job_id}?part=${name}`}
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
      <p className="mt-2 text-xs text-[#6b645c]">{hint ?? liveLine(paper)}</p>
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
