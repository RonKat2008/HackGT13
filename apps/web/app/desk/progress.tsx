"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  EXAMPLE_JOB_ID,
  type ConferenceDesk,
  type ConferenceProgress,
  type Paper,
} from "@/lib/desk";
import type { DeskVoiceAction } from "./voice-action";
import {
  categoryLines,
  failureWhere,
  findingCount,
  legendLine,
  paperLabel,
  summaryLine,
  summaryOf,
  verdictTone,
} from "@/lib/verdict";
import { AskDesk } from "./[id]/ask";
import { MorphLink } from "./morph-link";
import { LABELS, ORDER } from "./specialists";

const POLL_MS = 2000;

export function conferenceProgressFromPapers(papers: Paper[]): ConferenceProgress {
  let done = 0;
  let findings = 0;
  let running = 0;
  let queued = 0;
  for (const paper of papers) {
    if (paper.status === "passed" || paper.status === "contradicted" || paper.status === "error") done += 1;
    if (paper.status === "contradicted") findings += 1;
    if (paper.status === "running") running += 1;
    if (paper.status === "queued") queued += 1;
  }
  return {
    papers_total: papers.length,
    papers_done: done,
    papers_with_findings: findings,
    papers_running: running,
    papers_queued: queued,
  };
}

export function conferenceProgressLine(progress?: ConferenceProgress, papers: Paper[] = []): string {
  const counts = progress ?? conferenceProgressFromPapers(papers);
  return `${counts.papers_done} complete · ${counts.papers_with_findings} with findings · ${counts.papers_running} running`;
}

export function conferenceQueueActive(papers: Paper[], progress?: ConferenceProgress): boolean {
  if ((progress?.papers_running ?? 0) + (progress?.papers_queued ?? 0) > 0) return true;
  return papers.some((paper) => paper.status === "queued" || paper.status === "running");
}

function keepExample(next: Paper[], current: Paper[]): Paper[] {
  const sample = current.find((paper) => paper.job_id === EXAMPLE_JOB_ID);
  if (!sample || next.some((paper) => paper.job_id === EXAMPLE_JOB_ID)) return next;
  return [sample, ...next];
}

export function useConferenceDesk(
  conferenceId: string,
  initialPapers: Paper[],
  initialProgress?: ConferenceProgress,
  example = false,
) {
  const [papers, setPapers] = useState(initialPapers);
  const [progress, setProgress] = useState(initialProgress);
  const moving = conferenceQueueActive(papers, progress);

  useEffect(() => {
    setPapers(initialPapers);
    setProgress(initialProgress);
  }, [initialPapers, initialProgress]);

  useEffect(() => {
    if (!moving) return;
    let cancelled = false;
    const timer = setInterval(async () => {
      const response = await fetch(`/api/desk/conferences/${conferenceId}`);
      if (!response.ok || cancelled) return;
      const body = (await response.json()) as ConferenceDesk;
      if (!Array.isArray(body.papers) || cancelled) return;
      setPapers((current) => (example ? keepExample(body.papers, current) : body.papers));
      setProgress((current) => body.progress ?? current);
    }, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [conferenceId, moving, example]);

  return { papers, progress };
}

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

export function DeskViews({
  conferenceId,
  conferenceName,
  initial,
  initialProgress,
  example = false,
  initialView = "chat",
}: {
  conferenceId: string;
  conferenceName: string;
  initial: Paper[];
  initialProgress?: ConferenceProgress;
  example?: boolean;
  initialView?: "chat" | "summary";
}) {
  const router = useRouter();
  const [view, setView] = useState<"chat" | "summary">(example || initialView === "summary" ? "summary" : "chat");
  const { papers, progress } = useConferenceDesk(conferenceId, initial, initialProgress, example);
  const counts = conferenceProgressLine(progress, papers);

  useEffect(() => {
    function onVoice(event: Event) {
      const action = (event as CustomEvent<DeskVoiceAction>).detail;
      if (action?.type === "prompt") {
        setView("chat");
        return;
      }
      if (action?.type === "show" && (action.view === "summary" || action.view === "chat")) {
        setView(action.view);
      }
    }
    window.addEventListener("desk-voice", onVoice);
    return () => window.removeEventListener("desk-voice", onVoice);
  }, []);

  function selectView(next: "chat" | "summary") {
    setView(next);
    const params = new URLSearchParams(window.location.search);
    params.set("view", next);
    router.replace(`/desk/${conferenceId}?${params.toString()}`, { scroll: false });
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <p className="shrink-0 px-4 pt-3 text-[11px] text-[#6b645c]">{counts}</p>
      <div role="tablist" aria-label="Desk view" className="flex shrink-0 items-end gap-1 border-b border-[#e4dcd0] px-4">
        <TabButton id="chat" selected={view === "chat"} onSelect={() => selectView("chat")}>
          Chat
        </TabButton>
        <TabButton id="summary" selected={view === "summary"} onSelect={() => selectView("summary")}>
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
        <Summary conferenceId={conferenceId} papers={papers} counts={counts} />
      </div>
    </div>
  );
}

function dot(status: string): string {
  if (status === "contradicted" || status === "error") return "bg-[#8c3a2f]";
  if (status === "passed") return "bg-[#2f6b4f]";
  if (status === "running") return "bg-[#c4a15a]";
  return "bg-[#cfc6b8]";
}

export function ConferenceCount({
  conferenceId,
  initialPapers,
  initialProgress,
  example = false,
}: {
  conferenceId: string;
  initialPapers: Paper[];
  initialProgress?: ConferenceProgress;
  example?: boolean;
}) {
  const { papers, progress } = useConferenceDesk(conferenceId, initialPapers, initialProgress, example);
  return <p className="mt-1 text-[11px] text-[#6b645c]">{conferenceProgressLine(progress, papers)}</p>;
}

export function PaperRows({
  conferenceId,
  initialPapers,
  initialProgress,
  activeJobId,
  example = false,
  remove,
}: {
  conferenceId: string;
  initialPapers: Paper[];
  initialProgress?: ConferenceProgress;
  activeJobId?: string;
  example?: boolean;
  remove: (formData: FormData) => void | Promise<void>;
}) {
  const { papers } = useConferenceDesk(conferenceId, initialPapers, initialProgress, example);

  return (
    <ul className="relative z-0 flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto">
      {papers.map((paper) => {
        const active = paper.job_id === activeJobId;
        const title = paper.title || "Unread paper";
        return (
          <li key={paper.job_id} className="flex shrink-0 items-start gap-1 lg:shrink">
            <MorphLink
              href={`/desk/${conferenceId}/${paper.job_id}${paper.job_id === EXAMPLE_JOB_ID ? "?example=1" : ""}`}
              className={`flex min-w-0 flex-1 items-start gap-2 rounded-xl px-2 py-2 ${active ? "bg-white/80" : "hover:bg-white/60"}`}
            >
              <span
                className={`mt-1.5 size-1.5 shrink-0 rounded-full ${dot(paper.status)} ${paper.status === "running" ? "desk-pulse" : ""}`}
              />
              <span className="min-w-0">
                <span className="block text-sm leading-5">{title}</span>
                <span className="text-[11px] text-[#6b645c]">
                  {paper.arxiv_id}
                  {paper.status === "passed" || paper.status === "contradicted" || paper.status === "error" ? (
                    <>
                      {" · "}
                      <span className={verdictTone(paper.status)}>{paperLabel(paper)}</span>
                    </>
                  ) : null}
                </span>
              </span>
            </MorphLink>
            <form action={remove} className="shrink-0 pt-1">
              <input type="hidden" name="job_id" value={paper.job_id} />
              <input type="hidden" name="open" value={active ? "1" : ""} />
              <button
                type="submit"
                className="px-1 py-1 text-[11px] text-[#6b645c] underline decoration-[#c4a15a] underline-offset-4"
              >
                Delete
              </button>
            </form>
          </li>
        );
      })}
    </ul>
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

function Summary({
  conferenceId,
  papers,
  counts,
}: {
  conferenceId: string;
  papers: Paper[];
  counts: string;
}) {
  return (
    <section aria-label="Paper summary" className="min-h-0 flex-1 overflow-y-auto px-4 py-6 lg:px-8">
      <p className="mx-auto mb-4 max-w-3xl text-[11px] text-[#6b645c]">{counts}</p>
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
