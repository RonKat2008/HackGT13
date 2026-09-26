"use client";

import { useState } from "react";
import type { Issue, Paper } from "@/lib/desk";
import { findingSentence, verdictLabel, verdictTone } from "@/lib/verdict";
import { PdfView } from "../../../pdf-view";

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
  const [selected, setSelected] = useState(0);
  const issue = paper.issues[selected] ?? paper.issues[0];
  const title = paper.title || paper.arxiv_id;
  const sentence = findingSentence(paper.issues);

  return (
    <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
      <div className="min-h-[28rem] min-w-0 flex-1 lg:min-h-0">
        <PdfView
          jobId={paper.job_id}
          page={typeof issue?.page === "number" ? issue.page : null}
          quote={issue ? quoteOf(issue) : ""}
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
        {sentence ? <p className="mt-6 text-sm leading-6 text-[#1c1915]">{sentence}</p> : null}
        {paper.issues.length === 0 ? (
          <p className="mt-6 text-sm leading-6 text-[#1c1915]">
            No finding on this paper. A citation, a number, a support check, and a rerun did not fail.
          </p>
        ) : (
          <ol className={`${sentence ? "mt-4" : "mt-6"} flex flex-col gap-3`}>
            {paper.issues.map((item, index) => {
              const quote = quoteOf(item);
              const active = index === selected;
              return (
                <li key={`${item.issue_type}-${index}`}>
                  <button
                    type="button"
                    onClick={() => setSelected(index)}
                    aria-pressed={active}
                    className={`w-full rounded-2xl px-3 py-3 text-left ring-1 ${
                      active ? "bg-white ring-[#c4a15a]" : "bg-transparent ring-[#e4dcd0]"
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
        )}
      </aside>
    </div>
  );
}
