"use client";

import { useEffect, useState } from "react";
import type { Claim, Issue, Paper } from "@/lib/desk";
import { claimVerdictLabel, isFinding } from "@/lib/verdict";
import { FindingCard } from "./finding";

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
  if (paper.status === "running" && paper.specialist === name) return "now";
  if (finishedDetail(paper, name) || paper.events.some((event) => event.specialist === name && event.state === "finished")) {
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
  onViewEvidence?: (page: number | null) => void;
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
      <div className="mt-6 border-t border-[#e4dcd0] pt-4">
        {paper.status === "passed" && paper.issues.length === 0 ? (
          <p className="text-sm leading-6 text-[#1c1915]">
            No citation gap, missing number, unsupported claim, or failed rerun.
          </p>
        ) : null}
        {paper.status === "error" ? (
          <p className="text-sm leading-6 text-[#8c3a2f]">
            {failed?.detail || "This paper could not be read."}
          </p>
        ) : null}
        {(paper.claims ?? []).length > 0 && onSelectClaim ? (
          <ClaimList
            paper={paper}
            selectedClaimId={selectedClaimId}
            onSelectClaim={onSelectClaim}
            onViewEvidence={onViewEvidence}
          />
        ) : null}
        {(paper.claims ?? []).length === 0 && paper.issues.length > 0 ? (
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

function ClaimList({
  paper,
  selectedClaimId,
  onSelectClaim,
  onViewEvidence,
}: {
  paper: Paper;
  selectedClaimId: string;
  onSelectClaim: (claimId: string) => void;
  onViewEvidence?: (page: number | null) => void;
}) {
  const claims = orderedClaims(paper);
  const findings = claims.filter((claim) => isFinding(claim));
  const supported = claims.filter((claim) => !isFinding(claim));
  return (
    <div className="flex flex-col gap-4">
      <ClaimGroup
        label="Findings"
        claims={findings}
        selectedClaimId={selectedClaimId}
        onSelectClaim={onSelectClaim}
        onViewEvidence={onViewEvidence}
      />
      <ClaimGroup
        label="Supported"
        claims={supported}
        selectedClaimId={selectedClaimId}
        onSelectClaim={onSelectClaim}
        onViewEvidence={onViewEvidence}
      />
    </div>
  );
}

function ClaimGroup({
  label,
  claims,
  selectedClaimId,
  onSelectClaim,
  onViewEvidence,
}: {
  label: string;
  claims: Claim[];
  selectedClaimId: string;
  onSelectClaim: (claimId: string) => void;
  onViewEvidence?: (page: number | null) => void;
}) {
  if (claims.length === 0) return null;
  return (
    <div>
      <p className="text-[11px] tracking-[0.12em] text-[#6b645c]">{label}</p>
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
                  <span className="text-[11px] tracking-[0.12em] text-[#8a6a2f]">{claimVerdictLabel(claim.verdict)}</span>
                  <span className="mt-1 block text-sm leading-5 text-[#1c1915]">{claim.text}</span>
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </div>
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
