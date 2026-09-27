"use client";

import { useEffect, useState } from "react";
import type { Claim, Issue, Paper, PaperProgress } from "@/lib/desk";
import { isFinding } from "@/lib/verdict";
import progressFixture from "./fixtures/progress.json";
import { FindingCard, reviewKind, reviewResult } from "./finding";

export const ORDER = [
  "parse",
  "claims",
  "evidence",
  "citations",
  "numbers",
  "tables",
  "dataset",
  "reproduce",
  "verify",
  "critic",
  "stamp",
] as const;

export const LABELS: Record<string, string> = {
  parse: "Parse",
  claims: "Claims",
  evidence: "Evidence",
  citations: "Citations",
  numbers: "Numbers",
  tables: "Tables",
  dataset: "Dataset",
  reproduce: "Reproduce",
  verify: "Verify",
  critic: "Critic",
  stamp: "Stamp",
};

export function finishedDetail(paper: Paper, name: string): string {
  const event = [...paper.events]
    .reverse()
    .find((item) => item.specialist === name && item.state === "finished");
  if (!event || !event.detail || event.detail === name) return "";
  return event.detail;
}

const ROUND2_WINDOW =
  /round\s*2[^.\n]*(widen(?:ed|ing)?|span\s*window)|widen(?:ed|ing)?[^.\n]*round\s*2/i;

function mentionsRound2Window(text: string): boolean {
  return ROUND2_WINDOW.test(text);
}

/** Critic row sentence: prefer the finished event detail; else the Round 2 window line when present. */
export function specialistSentence(paper: Paper, name: string): string {
  const detail = finishedDetail(paper, name);
  if (name !== "critic") return detail;
  if (detail) return detail;
  const fromEvents = paper.events.some(
    (event) => event.specialist === "critic" && event.detail && mentionsRound2Window(event.detail),
  );
  const fromSteps = (paper.claims ?? []).some((claim) =>
    (claim.steps ?? []).some((step) => mentionsRound2Window(step)),
  );
  if (fromEvents || fromSteps) return "Round 2: widened window";
  return "";
}

function outcome(paper: Paper, name: string): "fail" | "pass" | "open" {
  if (cardState(paper, name) !== "done") return "open";
  if (paper.events.some((event) => event.specialist === name && event.state === "failed")) return "fail";
  const types = ISSUE_OF[name] ?? [];
  if (types.length > 0 && paper.issues.some((issue) => types.includes(issue.issue_type))) return "fail";
  return "pass";
}

function cardState(paper: Paper, name: string): "idle" | "now" | "done" {
  const started = paper.events.some((event) => event.specialist === name && event.state === "started");
  const finished =
    Boolean(finishedDetail(paper, name)) ||
    paper.events.some((event) => event.specialist === name && event.state === "finished");
  if (name === "reproduce" && paper.status === "running" && started && !finished) return "now";
  if (paper.status === "running" && paper.specialist === name) return "now";
  if (finished) {
    return "done";
  }
  if (paper.status === "passed" || paper.status === "contradicted") return "done";
  return "idle";
}

const ISSUE_OF: Record<string, string[]> = {
  evidence: ["support"],
  citations: ["citation"],
  numbers: ["number"],
  tables: ["table"],
  dataset: ["dataset"],
  reproduce: ["test"],
  verify: ["semantic"],
  stamp: ["citation", "number", "support", "dataset", "test", "table", "semantic"],
  result: ["citation", "number", "support", "dataset", "test", "table", "semantic"],
};

export function issueIndexForPart(paper: Paper, part: string): number {
  const types = ISSUE_OF[part] ?? [];
  return paper.issues.findIndex((issue) => types.includes(issue.issue_type));
}

export function orderedClaims(paper: Paper): Claim[] {
  const claims = paper.claims ?? [];
  const findings = claims.filter((claim) => isFinding(claim));
  const supported = claims.filter(
    (claim) => !isFinding(claim) && (claim.verdict === "supported" || claim.verdict === "reproduced"),
  );
  const rest = claims.filter((claim) => !findings.includes(claim) && !supported.includes(claim));
  return [...findings, ...supported, ...rest];
}

function hasVerdict(claim: Claim): boolean {
  return typeof claim.verdict === "string" && claim.verdict.length > 0;
}

/** Live claims for the rail. Never stored — a later poll can move a card. */
export function railClaims(paper: Paper): Claim[] {
  return paper.claims ?? [];
}

function paperForRail(paper: Paper, focus: string): Paper {
  if (paper.progress || focus !== "progress") return paper;
  return { ...paper, progress: progressFixture.paper as PaperProgress };
}

export function Specialists({
  paper,
  selected,
  onSelect,
  focus = "",
  selectedClaimId = "",
  onSelectClaim,
  onViewEvidence,
}: {
  paper: Paper;
  selected: number;
  onSelect: (index: number) => void;
  focus?: string;
  selectedClaimId?: string;
  onSelectClaim?: (claimId: string) => void;
  onViewEvidence?: (page: number | null, text?: string) => void;
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

  const live = paperForRail(paper, focus);
  const claims = railClaims(live);
  const hasVerdictedClaims = claims.some(hasVerdict);
  const railPaper = claims === (live.claims ?? []) ? live : { ...live, claims };
  const [traceOpen, setTraceOpen] = useState(false);

  return (
    <aside className="flex h-full min-h-0 w-full flex-col overflow-y-auto border-[#e4dcd0] bg-[#f7f3ea] px-4 py-4 lg:w-96 lg:border-l">
      <p className="sr-only" aria-live="polite">
        {announcement}
      </p>
      {hasVerdictedClaims && onSelectClaim ? (
        <ClaimList
          paper={railPaper}
          selectedClaimId={selectedClaimId}
          onSelectClaim={onSelectClaim}
          onViewEvidence={onViewEvidence}
        />
      ) : null}
      {paper.status === "passed" && paper.issues.length === 0 && !hasVerdictedClaims ? (
        <p className="text-sm leading-6 text-[#1c1915]">Nothing on this paper needs a second look.</p>
      ) : null}
      {paper.status === "error" ? (
        <p className="text-sm leading-6 text-[#8c3a2f]">
          {failed?.detail || "This paper could not be read."}
        </p>
      ) : null}
      {!hasVerdictedClaims && paper.issues.length > 0 ? (
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
                <span className="mt-1 block text-sm leading-5 text-[#1c1915]">{issue.reason}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      <details
        className={hasVerdictedClaims ? "mt-6 border-t border-[#e4dcd0] pt-4" : ""}
        open={traceOpen}
        onToggle={(event) => setTraceOpen(event.currentTarget.open)}
      >
        <summary className="cursor-pointer text-sm text-[#1c1915]">How this was read</summary>
        <ol className="mt-4 flex flex-col gap-3">
        {[...ORDER]
          .sort((a, b) => {
            const rank = { fail: 0, open: 1, pass: 2 };
            return rank[outcome(paper, a)] - rank[outcome(paper, b)];
          })
          .map((name) => {
            const state = cardState(paper, name);
            const result = outcome(paper, name);
            const sentence = specialistSentence(paper, name);
            const tone =
              result === "fail" ? "text-[#8c3a2f]" : result === "pass" ? "text-[#2f6b4f]" : "text-[#1c1915]";
            return (
              <li
                key={name}
                className={`${state === "done" ? "desk-rise" : ""} ${focus === name ? "rounded-xl bg-white px-2 py-2 ring-1 ring-[#c4a15a]" : ""}`}
              >
                <p className={`text-sm font-semibold ${tone}`}>{LABELS[name]}</p>
                {state === "now" ? <span className="desk-rule mt-1" /> : null}
                {state === "now" ? (
                  <p className="mt-1 flex items-center gap-2 text-xs text-[#8a6a2f]">
                    <span className="desk-pulse inline-block size-1.5 rounded-full bg-[#c4a15a]" />
                    now
                  </p>
                ) : null}
                {state === "done" && sentence ? (
                  <p className={`mt-1 text-xs leading-5 ${tone}`}>{sentence}</p>
                ) : null}
              </li>
            );
          })}
        </ol>
      </details>
    </aside>
  );
}

function ClaimList({
  paper,
  selectedClaimId,
  onSelectClaim,
  onViewEvidence,
}: {
  paper: Paper;
  selectedClaimId: string;
  onSelectClaim: (claimId: string) => void;
  onViewEvidence?: (page: number | null, text?: string) => void;
}) {
  const claims = orderedClaims(paper);
  const taken = new Set<string>();
  function take(match: (claim: Claim) => boolean): Claim[] {
    const group = claims.filter((claim) => !taken.has(claim.claim_id) && match(claim));
    for (const claim of group) taken.add(claim.claim_id);
    return group;
  }
  const toCheck = take(
    (claim) =>
      claim.verdict === "contradicted" ||
      claim.verdict === "could_not_reproduce" ||
      claim.verdict === "unresolved",
  );
  const needsPerson = take(
    (claim) => claim.verdict === "insufficient_evidence" || isFinding(claim),
  );
  const holds = take((claim) => claim.verdict === "supported" || claim.verdict === "reproduced");
  const rest = take(() => true);
  return (
    <div className="flex flex-col gap-5">
      <ClaimGroup
        label="To check"
        hint="Open these before you trust the paper."
        tone="text-[#8c3a2f]"
        claims={toCheck}
        selectedClaimId={selectedClaimId}
        onSelectClaim={onSelectClaim}
        onViewEvidence={onViewEvidence}
      />
      <ClaimGroup
        label="Needs a person"
        hint="The read did not settle these."
        tone="text-[#8a6a2f]"
        claims={needsPerson}
        selectedClaimId={selectedClaimId}
        onSelectClaim={onSelectClaim}
        onViewEvidence={onViewEvidence}
      />
      <ClaimGroup
        label="Holds"
        tone="text-[#2f6b4f]"
        claims={holds}
        collapsed
        selectedClaimId={selectedClaimId}
        onSelectClaim={onSelectClaim}
        onViewEvidence={onViewEvidence}
      />
      <ClaimGroup
        label="Not checked"
        tone="text-[#6b645c]"
        claims={rest}
        collapsed
        selectedClaimId={selectedClaimId}
        onSelectClaim={onSelectClaim}
        onViewEvidence={onViewEvidence}
      />
    </div>
  );
}

function ClaimGroup({
  label,
  hint,
  tone,
  claims,
  collapsed = false,
  selectedClaimId,
  onSelectClaim,
  onViewEvidence,
}: {
  label: string;
  hint?: string;
  tone: string;
  claims: Claim[];
  collapsed?: boolean;
  selectedClaimId: string;
  onSelectClaim: (claimId: string) => void;
  onViewEvidence?: (page: number | null, text?: string) => void;
}) {
  const selectedHere = claims.some((claim) => claim.claim_id === selectedClaimId);
  const [open, setOpen] = useState(!collapsed || selectedHere);
  useEffect(() => {
    if (selectedHere) setOpen(true);
  }, [selectedHere]);
  if (claims.length === 0) return null;
  return (
    <section>
      {collapsed ? (
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((current) => !current)}
          className="text-sm text-[#1c1915]"
        >
          {label} · {claims.length}
        </button>
      ) : (
        <div>
          <h2 className="text-sm text-[#1c1915]">
            {label} · {claims.length}
          </h2>
          {hint ? <p className="mt-1 text-xs leading-5 text-[#6b645c]">{hint}</p> : null}
        </div>
      )}
      {open ? (
        <ul className="mt-2 flex flex-col gap-2">
          {claims.map((claim) => {
            const active = claim.claim_id === selectedClaimId;
            return (
              <li key={claim.claim_id}>
                {active ? (
                  <FindingCard claim={claim} onViewEvidence={onViewEvidence} />
                ) : (
                  <button
                    type="button"
                    onClick={() => onSelectClaim(claim.claim_id)}
                    aria-pressed={active}
                    className="w-full rounded-2xl bg-transparent px-3 py-3 text-left ring-1 ring-[#e4dcd0]"
                  >
                    <span className="text-xs text-[#6b645c]">
                      {reviewKind(claim)}
                      {claim.page ? ` · page ${claim.page}` : ""}
                    </span>
                    <span className="mt-1 block font-[family-name:var(--desk-serif)] text-sm leading-5 text-[#1c1915]">
                      {claim.text}
                    </span>
                    <span className={`mt-2 block text-sm leading-5 ${tone}`}>{reviewResult(claim)}</span>
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
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
