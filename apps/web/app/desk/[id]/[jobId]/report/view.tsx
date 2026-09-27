"use client";

import { useState } from "react";
import { ReportVoice } from "./voice";
import type { Claim, Issue, Paper } from "@/lib/desk";
import {
  categoryLines,
  claimTypeLabel,
  claimVerdictLabel,
  findingSentence,
  isFinding,
  legendLine,
  summaryLine,
  summaryOf,
  verdictLabel,
  verdictTone,
} from "@/lib/verdict";
import { evidencePage, FindingCard } from "../../../finding";
import { PdfView, type PdfMark } from "../../../pdf-view";
import { orderedClaims } from "../../../specialists";

const KIND: Record<string, string> = {
  citation: "Citation",
  number: "Number",
  support: "Support",
  dataset: "Dataset",
  test: "Rerun",
};

const SECTIONS = [
  { id: "person", label: "Needs a person" },
  { id: "citation", label: "Citations" },
  { id: "number", label: "Numbers" },
  { id: "gain", label: "Gains" },
  { id: "dataset", label: "Datasets" },
  { id: "statement", label: "Statements" },
] as const;

type SectionId = (typeof SECTIONS)[number]["id"];

const SECTION_COPY: Record<SectionId, string> = {
  person:
    "These sentences never received a confident verdict. Open one to see what the desk compared and what a chair should decide. A row here asks for a person. It does not mark the sentence false.",
  citation:
    "Each citation is matched to the bibliography, then searched in Crossref, OpenAlex, and Semantic Scholar. Resolved means a strong title match. Unresolved means every catalog answered and none matched.",
  number:
    "Abstract numbers are checked against the results section and the rest of the PDF, including table cells. A missing number is one that appears in the abstract and nowhere else.",
  gain:
    "A claimed improvement is scored against the nearest table with an Ours row. When that table exists, the card shows the formula. With no such table, the gain stays unchecked.",
  dataset:
    "Dataset sentences wait for a rerun of a public table. Reproduced means the public count matched. Could not reproduce means the rerun disagreed.",
  statement:
    "These are the paper’s own “we show” sentences. A supported row shares its wording with the methods or results, or Jev accepted the nearby passage.",
};

function quoteOf(issue: Issue): string {
  return issue.evidence_span || issue.claim_text;
}

function needsPerson(claim: Claim): boolean {
  if (claim.verdict === "insufficient_evidence") return true;
  return isFinding(claim) && claim.verdict === "not_mentioned";
}

function inSection(claim: Claim, section: SectionId): boolean {
  if (section === "person") return needsPerson(claim);
  if (section === "citation") return claim.claim_type === "citation";
  if (section === "number") return claim.claim_type === "numerical";
  if (section === "gain") return claim.claim_type === "numerical_comparison";
  if (section === "dataset") return claim.claim_type === "dataset";
  return claim.claim_type === "semantic" && !needsPerson(claim);
}

function personExplanation(claim: Claim): string {
  const rounds = claim.rounds > 0 ? claim.rounds : 1;
  const times = rounds === 1 ? "once" : `${rounds} times`;
  const confidence = `${Math.round((claim.confidence || 0) * 100)}%`;
  return `The desk read this sentence ${times} against nearby passages and stayed unsure, at ${confidence} confidence. Compare the sentence with the marked page. A true line can land here when the passage in front of the judge is too short to confirm it.`;
}

function openClaim(
  claim: Claim,
  setClaimId: (id: string) => void,
  setFocusPage: (page: number | null) => void,
  setFocusText: (text: string) => void,
) {
  setClaimId(claim.claim_id);
  setFocusPage(claim.page ?? evidencePage(claim));
  setFocusText(claim.text);
}

export function ReportView({ paper }: { paper: Paper }) {
  const claims = orderedClaims(paper);
  const first = SECTIONS.find((section) => claims.some((claim) => inSection(claim, section.id)))?.id ?? "person";
  const [section, setSection] = useState<SectionId>(first);
  const visible = claims.filter((claim) => inSection(claim, section));
  const [claimId, setClaimId] = useState(visible[0]?.claim_id ?? "");
  const [selected, setSelected] = useState(0);
  const [focusPage, setFocusPage] = useState<number | null>(null);
  const [focusText, setFocusText] = useState("");
  const active = visible.find((claim) => claim.claim_id === claimId) ?? visible[0];
  const issue = paper.issues[selected] ?? paper.issues[0];
  const title = paper.title || paper.arxiv_id;
  const sentence = findingSentence(paper.issues);
  const summary = summaryOf(paper);
  const line = summaryLine(summary);
  const categories = categoryLines(summary).filter((item) => item.total > 0);
  const marks: PdfMark[] = active
    ? [
        { page: active.page, text: active.text, role: "claim" },
        ...active.evidence
          .filter((item) => item.text.trim() && !item.text.startsWith("Neighbor window"))
          .map((item) => ({ page: item.page, text: item.text, role: item.role })),
      ]
    : [];

  function choose(next: SectionId) {
    setSection(next);
    const row = claims.find((claim) => inSection(claim, next));
    if (!row) {
      setClaimId("");
      return;
    }
    openClaim(row, setClaimId, setFocusPage, setFocusText);
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
      <div className="min-h-[28rem] min-w-0 flex-1 lg:min-h-0">
        <PdfView
          jobId={paper.job_id}
          page={active ? null : typeof issue?.page === "number" ? issue.page : null}
          quote={active ? "" : issue ? quoteOf(issue) : ""}
          marks={active ? marks : undefined}
          focusPage={active ? (focusPage ?? active.page ?? evidencePage(active)) : typeof issue?.page === "number" ? issue.page : null}
          focusText={focusText}
        />
      </div>
      <aside className="flex min-h-0 w-full flex-col overflow-y-auto border-t border-[#e4dcd0] bg-[#f7f3ea] px-4 py-4 lg:w-[26rem] lg:border-l lg:border-t-0">
        <p className="text-[11px] tracking-[0.16em] text-[#8c3a2f]">REPORT</p>
        <h1 className="mt-3 font-[family-name:var(--desk-serif)] text-2xl leading-tight">{title}</h1>
        <p className="mt-2 text-xs text-[#6b645c]">
          {paper.arxiv_id}
          {paper.author_name ? ` · ${paper.author_name}` : ""}
          {" · "}
          <span className={verdictTone(paper.status)}>{verdictLabel(paper.status)}</span>
        </p>
        {line ? <p className="mt-4 text-sm leading-6 text-[#1c1915]">{line}</p> : null}
        {legendLine(summary) ? <p className="mt-1 text-xs leading-5 text-[#6b645c]">{legendLine(summary)}</p> : null}
        <ReportVoice jobId={paper.job_id} claim={active?.text ?? ""} />
        {categories.length > 0 ? (
          <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-[11px] text-[#6b645c]">
            {categories.map((item) => (
              <div key={item.label}>
                <dt className="tracking-[0.04em]">{item.label}</dt>
                <dd className="text-sm text-[#1c1915]">{item.value}</dd>
              </div>
            ))}
          </dl>
        ) : null}

        {claims.length > 0 ? (
          <>
            <div role="tablist" aria-label="Claim sections" className="mt-5 flex flex-wrap gap-2">
              {SECTIONS.map((item) => {
                const count = claims.filter((claim) => inSection(claim, item.id)).length;
                const on = section === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    role="tab"
                    aria-selected={on}
                    onClick={() => choose(item.id)}
                    className={`rounded-full px-3 py-1.5 text-xs ${
                      on ? "bg-[#1c1915] text-[#f4f0e6]" : "bg-white text-[#1c1915] ring-1 ring-[#e4dcd0]"
                    }`}
                  >
                    {item.label}
                    <span className={on ? "text-[#c4a15a]" : "text-[#6b645c]"}> {count}</span>
                  </button>
                );
              })}
            </div>
            <p className="mt-3 text-sm leading-6 text-[#6b645c]">{SECTION_COPY[section]}</p>
            {visible.length === 0 ? (
              <p className="mt-4 text-sm leading-6 text-[#1c1915]">Nothing in this section.</p>
            ) : (
              <ol className="mt-4 flex flex-col gap-3">
                {visible.map((claim) => {
                  const open = claim.claim_id === active?.claim_id;
                  return (
                    <li key={claim.claim_id}>
                      {open ? (
                        <div className="flex flex-col gap-3">
                          {section === "person" ? (
                            <p className="rounded-2xl bg-white px-3 py-3 text-sm leading-6 text-[#1c1915] ring-1 ring-[#e4dcd0]">
                              {personExplanation(claim)}
                            </p>
                          ) : null}
                          <FindingCard
                            claim={claim}
                            onViewEvidence={(nextPage, text) => {
                              setFocusPage(nextPage);
                              setFocusText(text ?? "");
                            }}
                          />
                        </div>
                      ) : (
                        <button
                          type="button"
                          onClick={() => openClaim(claim, setClaimId, setFocusPage, setFocusText)}
                          className="w-full rounded-2xl bg-transparent px-3 py-3 text-left ring-1 ring-[#e4dcd0]"
                        >
                          <span className="text-[11px] tracking-[0.12em] text-[#8a6a2f]">
                            {claimTypeLabel(claim.claim_type)} · {claimVerdictLabel(claim.verdict)}
                          </span>
                          <span className="mt-1 block text-sm leading-5">{claim.text}</span>
                        </button>
                      )}
                    </li>
                  );
                })}
              </ol>
            )}
          </>
        ) : paper.issues.length === 0 ? (
          <p className="mt-6 text-sm leading-6 text-[#1c1915]">
            No finding on this paper. A citation, a number, a support check, and a rerun did not fail.
          </p>
        ) : (
          <>
            {sentence ? <p className="mt-6 text-sm leading-6 text-[#1c1915]">{sentence}</p> : null}
            <ol className={`${sentence ? "mt-4" : "mt-6"} flex flex-col gap-3`}>
              {paper.issues.map((item, index) => {
                const quote = quoteOf(item);
                const activeIssue = index === selected;
                return (
                  <li key={`${item.issue_type}-${index}`}>
                    <button
                      type="button"
                      onClick={() => setSelected(index)}
                      aria-pressed={activeIssue}
                      className={`w-full rounded-2xl px-3 py-3 text-left ring-1 ${
                        activeIssue ? "bg-white ring-[#c4a15a]" : "bg-transparent ring-[#e4dcd0]"
                      }`}
                    >
                      <p className="text-[11px] tracking-[0.12em] text-[#8a6a2f]">
                        {KIND[item.issue_type] ?? item.issue_type}
                        {typeof item.page === "number" ? ` · Page ${item.page}` : ""}
                      </p>
                      {quote ? (
                        <blockquote className="mt-2 font-[family-name:var(--desk-serif)] text-sm leading-6">
                          {quote}
                        </blockquote>
                      ) : null}
                      <p className="mt-2 text-sm leading-5 text-[#1c1915]">{item.reason}</p>
                    </button>
                  </li>
                );
              })}
            </ol>
          </>
        )}
      </aside>
    </div>
  );
}
