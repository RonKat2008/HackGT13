"use client";

import { useState } from "react";
import type { Issue, Paper } from "@/lib/desk";
import {
  categoryLines,
  claimVerdictLabel,
  findingSentence,
  isFinding,
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

function quoteOf(issue: Issue): string {
  return issue.evidence_span || issue.claim_text;
}

export function ReportView({ paper }: { paper: Paper }) {
  const claims = orderedClaims(paper);
  const findings = claims.filter((claim) => isFinding(claim));
  const rest = claims.filter((claim) => !isFinding(claim));
  const [claimId, setClaimId] = useState(findings[0]?.claim_id ?? claims[0]?.claim_id ?? "");
  const [selected, setSelected] = useState(0);
  const [focusPage, setFocusPage] = useState<number | null>(null);
  const active = claims.find((claim) => claim.claim_id === claimId) ?? claims[0];
  const issue = paper.issues[selected] ?? paper.issues[0];
  const title = paper.title || paper.arxiv_id;
  const sentence = findingSentence(paper.issues);
  const summary = summaryOf(paper);
  const line = summaryLine(summary);
  const categories = categoryLines(summary).filter((item) => item.total > 0);
  const marks: PdfMark[] = active
    ? [
        { page: active.page, text: active.text, role: "claim" },
        ...active.evidence.filter((item) => item.text.trim()).map((item) => ({ page: item.page, text: item.text, role: item.role })),
      ]
    : [];

  return (
    <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
      <div className="min-h-[28rem] min-w-0 flex-1 lg:min-h-0">
        <PdfView
          jobId={paper.job_id}
          page={active ? null : typeof issue?.page === "number" ? issue.page : null}
          quote={active ? "" : issue ? quoteOf(issue) : ""}
          marks={active ? marks : undefined}
          focusPage={active ? (focusPage ?? evidencePage(active)) : typeof issue?.page === "number" ? issue.page : null}
        />
      </div>
      <aside className="flex min-h-0 w-full flex-col overflow-y-auto border-t border-[#e4dcd0] bg-[#f7f3ea] px-4 py-4 lg:w-80 lg:border-l lg:border-t-0">
        <p className="text-[11px] tracking-[0.16em] text-[#8c3a2f]">REPORT</p>
        <h1 className="mt-3 font-[family-name:var(--desk-serif)] text-2xl leading-tight">{title}</h1>
        <p className="mt-2 text-xs text-[#6b645c]">
          {paper.arxiv_id}
          {paper.author_name ? ` · ${paper.author_name}` : ""}
          {" · "}
          <span className={verdictTone(paper.status)}>{verdictLabel(paper.status)}</span>
        </p>
        {line ? <p className="mt-6 text-sm leading-6 text-[#1c1915]">{line}</p> : null}
        {categories.length > 0 ? (
          <dl className="mt-4 grid grid-cols-1 gap-y-2 text-[11px] text-[#6b645c]">
            {categories.map((item) => (
              <div key={item.label} className="flex items-baseline justify-between gap-3">
                <dt className="tracking-[0.04em]">{item.label}</dt>
                <dd className="text-sm text-[#1c1915]">{item.value}</dd>
              </div>
            ))}
          </dl>
        ) : null}
        {claims.length > 0 ? (
          <>
            {findings.length > 0 ? (
              <ol className="mt-6 flex flex-col gap-3">
                {findings.map((claim) => (
                  <li key={claim.claim_id}>
                    {claim.claim_id === active?.claim_id ? (
                      <FindingCard claim={claim} onViewEvidence={setFocusPage} />
                    ) : (
                      <button
                        type="button"
                        onClick={() => {
                          setClaimId(claim.claim_id);
                          setFocusPage(evidencePage(claim));
                        }}
                        className="w-full rounded-2xl px-3 py-3 text-left ring-1 ring-[#e4dcd0]"
                      >
                        <span className="text-[11px] tracking-[0.12em] text-[#8a6a2f]">{claimVerdictLabel(claim.verdict)}</span>
                        <span className="mt-1 block text-sm leading-5">{claim.text}</span>
                      </button>
                    )}
                  </li>
                ))}
              </ol>
            ) : null}
            {rest.length > 0 ? (
              <ul className={`${findings.length > 0 ? "mt-4" : "mt-6"} flex flex-col gap-2`}>
                {rest.map((claim) => (
                  <li key={claim.claim_id}>
                    <button
                      type="button"
                      onClick={() => {
                        setClaimId(claim.claim_id);
                        setFocusPage(evidencePage(claim));
                      }}
                      aria-pressed={claim.claim_id === active?.claim_id}
                      className={`w-full rounded-2xl px-3 py-2 text-left ring-1 ${
                        claim.claim_id === active?.claim_id ? "bg-white ring-[#c4a15a]" : "bg-transparent ring-[#e4dcd0]"
                      }`}
                    >
                      <span className="text-[11px] tracking-[0.12em] text-[#8a6a2f]">{claimVerdictLabel(claim.verdict)}</span>
                      <span className="mt-0.5 block text-sm leading-5 text-[#1c1915]">{claim.text}</span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
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
