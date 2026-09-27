"use client";

import { useMemo, useState, type ReactNode } from "react";
import type { Paper, Quote, TraceStep } from "@/lib/desk";
import { MorphLink } from "./morph-link";

const ISSUE_LABEL: Record<string, string> = {
  citation: "Citation",
  number: "Number",
  table: "Table",
  support: "Support",
  semantic: "Evidence",
  dataset: "Dataset",
  test: "Rerun",
};

const ISSUE_KIND =
  /^(citation|number|table|support|semantic|dataset|test):\s+(.+)$/i;

type OpenAction = {
  job_id?: string;
  arxiv_id?: string;
  title?: string;
  page?: number | null;
  text?: string;
};

type Finding = {
  id: string;
  issueType: string;
  reason: string;
  text: string;
  page: number | null;
  quote: Quote | null;
};

type PaperGroup = {
  key: string;
  title: string;
  arxivId: string;
  verdict: string;
  paper: Paper | null;
  findings: Finding[];
};

type ParsedLine = {
  title: string;
  arxivId: string;
  issueType: string;
  reason: string;
  verdict: string;
};

export function issueLabel(issueType: string): string {
  if (!issueType) return "Passage";
  return ISSUE_LABEL[issueType] ?? issueType.replaceAll("_", " ");
}

function paperName(paper: Paper): string {
  return paper.title || "Unread paper";
}

function verdictTone(label: string): string {
  const value = label.toLowerCase();
  if (value.startsWith("passed") || value.includes("nothing")) return "text-[#2f6b4f]";
  if (value.startsWith("failed") || value.includes("problem")) return "text-[#8c3a2f]";
  return "text-[#6b645c]";
}

function statusLabel(paper: Paper | null): string {
  if (!paper) return "";
  if (paper.status === "passed") return "Passed";
  if (paper.status === "contradicted") return "Failed";
  if (paper.status === "queued") return "Still queued";
  if (paper.status === "running") return "Still reading";
  if (paper.status === "error") return "Not read";
  return "";
}

function parseLine(line: string): ParsedLine | null {
  const desk = line.match(/^(.+?)\s+\(([0-9]{4}\.[0-9]{4,5}(?:v\d+)?)\)\s+(.+)$/);
  if (desk) {
    const title = desk[1].trim();
    const arxivId = desk[2];
    const rest = desk[3].trim();
    if (rest === "is still queued.") {
      return { title, arxivId, issueType: "", reason: "", verdict: "Still queued" };
    }
    if (rest === "has nothing to report.") {
      return { title, arxivId, issueType: "", reason: "", verdict: "Nothing to report" };
    }
    const kind = rest.match(ISSUE_KIND);
    if (!kind) return null;
    return {
      title,
      arxivId,
      issueType: kind[1].toLowerCase(),
      reason: kind[2].trim(),
      verdict: "",
    };
  }
  const author = line.match(/^(.+)\s+(citation|number|table|support|semantic|dataset|test):\s+(.+)$/i);
  if (!author) return null;
  return {
    title: author[1].trim(),
    arxivId: "",
    issueType: author[2].toLowerCase(),
    reason: author[3].trim(),
    verdict: "",
  };
}

function parseReport(text: string): ParsedLine[] | null {
  const lines = text.split("\n").map((line) => line.trim()).filter(Boolean);
  if (lines.length === 0) return null;
  const parsed = lines.map(parseLine);
  const hits = parsed.filter((line): line is ParsedLine => line !== null);
  if (hits.length === 0 || hits.length / lines.length < 0.6) return null;
  return hits;
}

function quoteFinding(quote: Quote): Finding {
  return {
    id: quote.quote_id,
    issueType: quote.issue_type,
    reason: quote.reason,
    text: quote.text,
    page: quote.page,
    quote,
  };
}

function buildGroups(
  text: string,
  quotes: Quote[],
  papers: Paper[],
  citedIds: string[],
): { groups: PaperGroup[]; dump: boolean } {
  const report = parseReport(text);
  const byArxiv = new Map(papers.map((paper) => [paper.arxiv_id, paper]));
  const order: string[] = [];
  function add(id: string) {
    if (id && !order.includes(id)) order.push(id);
  }
  for (const id of citedIds) add(id);
  for (const quote of quotes) add(quote.arxiv_id);
  for (const line of report ?? []) add(line.arxivId);

  const lonePaper = papers.length === 1 ? papers[0] : undefined;
  if (order.length === 0 && lonePaper && (report || quotes.length > 0)) add(lonePaper.arxiv_id);

  const groups = order.map((id) => {
    const paper = byArxiv.get(id) ?? (lonePaper && lonePaper.arxiv_id === id ? lonePaper : null);
    const lines = (report ?? []).filter((line) => (line.arxivId ? line.arxivId === id : true));
    const title =
      (paper ? paperName(paper) : "") ||
      quotes.find((quote) => quote.arxiv_id === id)?.title ||
      lines.find((line) => line.title)?.title ||
      id;
    const verdict =
      lines.find((line) => line.verdict)?.verdict ||
      statusLabel(paper);
    const issueQuotes = quotes.filter((quote) => quote.arxiv_id === id && quote.issue_type);
    let findings = issueQuotes.map(quoteFinding);
    if (findings.length === 0) {
      findings = lines
        .filter((line) => line.issueType)
        .map((line, index) => ({
          id: `line-${id || "paper"}-${index}`,
          issueType: line.issueType,
          reason: line.reason,
          text: "",
          page: null,
          quote: null,
        }));
    }
    return { key: id || title, title, arxivId: id, verdict, paper, findings };
  });

  const visible = groups.filter(
    (group) => group.paper || group.findings.length > 0 || citedIds.includes(group.arxivId),
  );
  return { groups: visible, dump: report !== null };
}

const KIND_ORDER = ["citation", "number", "table", "support", "semantic", "dataset", "test"];

const LINK = "underline decoration-[#c4a15a] decoration-[1.5px] underline-offset-4";

function sentence(text: string): string {
  const trimmed = text.replace(/\s+/g, " ").trim();
  if (!trimmed) return "";
  return /[.!?]$/.test(trimmed) ? trimmed : `${trimmed}.`;
}

function explainIssue(kind: string): string {
  switch (kind) {
    case "number":
      return "A figure is stated in one place and missing where the result should be, so that number cannot be checked.";
    case "citation":
      return "The reference does not resolve to a paper a reader can open.";
    case "support":
      return "The sentence is not backed by the methods or the results.";
    case "semantic":
      return "The wording does not match the passage it was checked against.";
    case "table":
      return "A table and the sentence that cites it do not agree.";
    case "dataset":
      return "The count does not match the public table.";
    case "test":
      return "The rerun did not reproduce the reported result.";
    default:
      return "The desk could not confirm this against the rest of the paper.";
  }
}

function kindHeading(kind: string, count: number): string {
  const label = issueLabel(kind);
  if (count === 1 || label === "Evidence" || label === "Support") return label;
  return `${label}s`;
}

function joinWords(words: string[]): string {
  if (words.length <= 1) return words[0] ?? "";
  if (words.length === 2) return `${words[0]} and ${words[1]}`;
  return `${words.slice(0, -1).join(", ")}, and ${words.at(-1)}`;
}

function issueFindings(group: PaperGroup): Finding[] {
  return group.findings.filter((finding) => finding.issueType);
}

function patternLine(findings: Finding[]): string {
  const counts = new Map<string, number>();
  for (const finding of findings) {
    counts.set(finding.issueType, (counts.get(finding.issueType) ?? 0) + 1);
  }
  const top = [...counts.entries()].sort((a, b) => b[1] - a[1])[0];
  if (!top) return "";
  const [kind, count] = top;
  if (findings.length === 1) return explainIssue(kind);
  if (kind === "number" && count >= 2) {
    return "Most of them are numbers in the abstract that never appear in the results.";
  }
  if (count === findings.length) return `All of them are ${issueLabel(kind).toLowerCase()} checks. ${explainIssue(kind)}`;
  return `The most common is ${issueLabel(kind).toLowerCase()}. ${explainIssue(kind)}`;
}

function writeSummary(groups: PaperGroup[]): { lead: string; detail: string } {
  const flagged = groups.filter((group) => issueFindings(group).length > 0);
  const findings = flagged.flatMap(issueFindings);
  const clear = groups.length - flagged.length;
  if (findings.length === 0) {
    return {
      lead: groups.length > 1 ? "Nothing in these papers failed a check." : "Nothing in this paper failed a check.",
      detail: "No citation, number, or claim was flagged.",
    };
  }
  const findingWord = findings.length === 1 ? "finding" : "findings";
  const paperWord = flagged.length === 1 ? "paper" : "papers";
  const clearLine =
    clear === 0 ? "" : clear === 1 ? " One paper had nothing to flag." : ` ${clear} papers had nothing to flag.`;
  return {
    lead: `${findings.length} ${findingWord} across ${flagged.length} ${paperWord}.`,
    detail: `${patternLine(findings)}${clearLine}`.trim(),
  };
}

function paperLead(group: PaperGroup): string {
  if (group.verdict === "Still queued" || group.verdict === "Still reading") {
    return "This paper has not been read yet, so there is nothing to check.";
  }
  if (group.verdict === "Not read") return "This paper could not be read.";
  const findings = issueFindings(group);
  if (findings.length === 0) return "This read did not fail a check.";
  const kinds = findingsByKind(findings).map((bucket) => {
    const label = issueLabel(bucket.kind);
    if (label === "Evidence" || label === "Support") return label.toLowerCase();
    return `${label.toLowerCase()}s`;
  });
  if (findings.length === 1) return `One check failed: ${kinds[0]}.`;
  return `${findings.length} checks failed, on ${joinWords(kinds)}.`;
}

function findingsByKind(findings: Finding[]): { kind: string; items: Finding[] }[] {
  const buckets = new Map<string, Finding[]>();
  for (const finding of findings) {
    const list = buckets.get(finding.issueType) ?? [];
    list.push(finding);
    buckets.set(finding.issueType, list);
  }
  const ordered = KIND_ORDER.filter((kind) => buckets.has(kind)).map((kind) => ({
    kind,
    items: buckets.get(kind) ?? [],
  }));
  for (const [kind, items] of buckets) {
    if (!KIND_ORDER.includes(kind)) ordered.push({ kind, items });
  }
  return ordered;
}

function blocksOf(text: string): Array<{ type: "p"; text: string } | { type: "ul"; items: string[] }> {
  const lines = text.split("\n").map((line) => line.trim()).filter(Boolean);
  const blocks: Array<{ type: "p"; text: string } | { type: "ul"; items: string[] }> = [];
  let list: string[] = [];
  function flush() {
    if (list.length === 0) return;
    blocks.push({ type: "ul", items: list });
    list = [];
  }
  for (const line of lines) {
    if (/^[-•]\s+/.test(line)) list.push(line.replace(/^[-•]\s+/, ""));
    else {
      flush();
      blocks.push({ type: "p", text: line });
    }
  }
  flush();
  return blocks;
}

function LinkedText({
  text,
  papers,
  onOpenPaper,
}: {
  text: string;
  papers: Paper[];
  onOpenPaper?: (paper: Paper, button: HTMLButtonElement) => void;
}) {
  if (!onOpenPaper || papers.length === 0) return <>{text}</>;
  const needles = papers
    .flatMap((paper) => {
      const title = paperName(paper);
      const marks: { paper: Paper; label: string }[] = [];
      if (title.length >= 8) marks.push({ paper, label: title }, { paper, label: `@${title}` });
      if (paper.arxiv_id) marks.push({ paper, label: paper.arxiv_id });
      return marks;
    })
    .sort((a, b) => b.label.length - a.label.length);
  const spans: { start: number; end: number; paper: Paper; label: string }[] = [];
  const taken = (start: number, end: number) => spans.some((span) => start < span.end && end > span.start);
  for (const needle of needles) {
    let from = 0;
    while (from < text.length) {
      const at = text.indexOf(needle.label, from);
      if (at < 0) break;
      const end = at + needle.label.length;
      if (!taken(at, end)) {
        spans.push({
          start: at,
          end,
          paper: needle.paper,
          label: needle.label.replace(/^@/, ""),
        });
      }
      from = end;
    }
  }
  if (spans.length === 0) return <>{text}</>;
  spans.sort((a, b) => a.start - b.start);
  const nodes: ReactNode[] = [];
  let cursor = 0;
  spans.forEach((span, index) => {
    if (span.start > cursor) nodes.push(text.slice(cursor, span.start));
    nodes.push(
      <button
        key={`${span.start}-${index}`}
        type="button"
        className={LINK}
        onClick={(event) => onOpenPaper(span.paper, event.currentTarget)}
      >
        {span.label}
      </button>,
    );
    cursor = span.end;
  });
  if (cursor < text.length) nodes.push(text.slice(cursor));
  return <>{nodes}</>;
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      viewBox="0 0 16 16"
      aria-hidden="true"
      className={`mt-0.5 h-4 w-4 shrink-0 text-[#6b645c] transition-transform duration-200 motion-reduce:transition-none ${open ? "rotate-90" : ""}`}
    >
      <path
        d="M6 3.5 11 8 6 12.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function Brief({
  groups,
  titles,
  conferenceId,
  pageAction,
  activeQuoteId,
  activeJobId,
  onOpenQuote,
  onOpenPaper,
}: {
  groups: PaperGroup[];
  titles: boolean;
  conferenceId?: string;
  pageAction?: OpenAction | null;
  activeQuoteId: string;
  activeJobId: string;
  onOpenQuote: (quote: Quote, button?: HTMLButtonElement | null) => void;
  onOpenPaper: (paper: Paper, button?: HTMLButtonElement | null) => void;
}) {
  const summary = writeSummary(groups);

  function openGroup(group: PaperGroup, button: HTMLButtonElement) {
    const pageForThis =
      pageAction && (pageAction.job_id === group.paper?.job_id || pageAction.arxiv_id === group.arxivId);
    if (pageForThis && pageAction?.job_id) {
      onOpenQuote(
        {
          quote_id: `bot-${pageAction.job_id}`,
          job_id: pageAction.job_id,
          arxiv_id: pageAction.arxiv_id || group.arxivId,
          title: pageAction.title || group.title,
          page: typeof pageAction.page === "number" ? pageAction.page : null,
          text: pageAction.text || "",
          issue_type: "",
          reason: "",
        },
        button,
      );
      return;
    }
    if (group.paper) onOpenPaper(group.paper, button);
  }

  return (
    <div className="flex flex-col gap-8">
      <section>
        <h3 className="font-[family-name:var(--desk-serif)] text-xl leading-tight text-[#1c1915]">Summary</h3>
        <p className="mt-2 text-sm leading-7 text-[#1c1915]">{summary.lead}</p>
        {summary.detail ? <p className="mt-2 text-sm leading-7 text-[#1c1915]">{summary.detail}</p> : null}
      </section>
      {groups.map((group) => {
        const findings = issueFindings(group);
        const activePaper = Boolean(group.paper && group.paper.job_id === activeJobId);
        const canOpen = Boolean(group.paper || pageAction?.job_id === group.paper?.job_id);
        return (
          <section key={group.key}>
            {titles ? (
              <>
                <h3 className="font-[family-name:var(--desk-serif)] text-xl leading-tight text-[#1c1915]">
                  {canOpen ? (
                    <button
                      type="button"
                      className={`${LINK} ${activePaper ? "decoration-2" : ""}`}
                      onClick={(event) => openGroup(group, event.currentTarget)}
                    >
                      {group.title}
                    </button>
                  ) : (
                    group.title
                  )}
                </h3>
                <p className="mt-1 text-xs leading-5 text-[#6b645c]">
                  {[group.arxivId, group.verdict].filter(Boolean).map((part, index) => (
                    <span key={`${group.key}-${index}`}>
                      {index > 0 ? " · " : ""}
                      <span className={part === group.verdict ? verdictTone(part) : undefined}>{part}</span>
                    </span>
                  ))}
                </p>
              </>
            ) : null}
            <p className={`${titles ? "mt-3" : "mt-2"} text-sm leading-7 text-[#1c1915]`}>{paperLead(group)}</p>
            {findingsByKind(findings).map((bucket) => (
              <div key={bucket.kind} className="mt-4">
                <h4 className="text-sm text-[#1c1915]">{kindHeading(bucket.kind, bucket.items.length)}</h4>
                <ul className="mt-2 flex list-disc flex-col gap-3 pl-5 text-sm leading-7 text-[#1c1915]">
                  {bucket.items.map((finding) => {
                    const reason = sentence(finding.reason || finding.text || "This check failed");
                    const active = activeQuoteId === finding.id;
                    const note = explainIssue(finding.issueType);
                    return (
                      <li key={finding.id}>
                        {finding.quote ? (
                          <button
                            type="button"
                            className={`text-left ${LINK} ${active ? "decoration-2" : ""}`}
                            onClick={(event) => onOpenQuote(finding.quote as Quote, event.currentTarget)}
                          >
                            {reason}
                          </button>
                        ) : (
                          <span>{reason}</span>
                        )}{" "}
                        {note !== reason ? note : null}
                        {finding.quote ? (
                          <button
                            type="button"
                            className={`ml-2 ${LINK} ${active ? "decoration-2" : ""}`}
                            onClick={(event) => onOpenQuote(finding.quote as Quote, event.currentTarget)}
                          >
                            {typeof finding.page === "number" ? `Page ${finding.page}` : "Open"}
                          </button>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
            {titles && conferenceId && group.paper ? (
              <MorphLink
                href={`/desk/${conferenceId}/${group.paper.job_id}`}
                className={`mt-3 inline-block text-xs text-[#6b645c] ${LINK}`}
              >
                Full paper
              </MorphLink>
            ) : null}
          </section>
        );
      })}
    </div>
  );
}


export function ChatReply({
  text,
  quotes,
  papers,
  citedIds,
  trace,
  layout = "papers",
  formula,
  pageAction,
  conferenceId,
  activeQuoteId = "",
  activeJobId = "",
  onOpenQuote,
  onOpenPaper,
}: {
  text: string;
  quotes: Quote[];
  papers: Paper[];
  citedIds: string[];
  trace: TraceStep[];
  layout?: "papers" | "findings";
  formula?: string;
  pageAction?: OpenAction | null;
  conferenceId?: string;
  activeQuoteId?: string;
  activeJobId?: string;
  onOpenQuote: (quote: Quote, button?: HTMLButtonElement | null) => void;
  onOpenPaper: (paper: Paper, button?: HTMLButtonElement | null) => void;
}) {
  const { groups, dump } = useMemo(
    () => buildGroups(text, quotes, papers, citedIds),
    [text, quotes, papers, citedIds],
  );
  const named = layout === "papers" || groups.length > 1;
  const [traceOpen, setTraceOpen] = useState(false);
  const lookedAt = trace.filter((step) => step.kind === "choose").length;
  const prose = dump ? "" : text.trim();
  const showBrief = dump ? groups.length > 0 : groups.some((group) => issueFindings(group).length > 0);

  return (
    <div className="desk-rise flex max-w-full flex-col gap-3">
      {lookedAt > 0 ? (
        <div>
          <button
            type="button"
            aria-expanded={traceOpen}
            onClick={() => setTraceOpen((open) => !open)}
            className="flex items-center gap-2 text-xs text-[#6b645c]"
          >
            <Chevron open={traceOpen} />
            Looked at {lookedAt} {lookedAt === 1 ? "paper" : "papers"}
          </button>
          {traceOpen ? (
            <ol className="mt-2 flex flex-col gap-1.5 border-l border-[#e4dcd0] pl-3">
              {trace.map((step) => (
                <li key={step.id} className="text-xs leading-5 text-[#6b645c]">
                  {step.kind === "quote" ? (
                    <button
                      type="button"
                      className={`text-left text-[#1c1915] ${LINK}`}
                      onClick={(event) => {
                        const quote = quotes.find((item) => item.quote_id === step.quote_id);
                        if (quote) onOpenQuote(quote, event.currentTarget);
                      }}
                    >
                      {issueLabel(step.label)}
                      {step.detail ? ` · ${step.detail}` : ""}
                    </button>
                  ) : (
                    <span>
                      {step.label}
                      {step.kind === "choose" && step.detail ? ` · ${step.detail}` : ""}
                    </span>
                  )}
                </li>
              ))}
            </ol>
          ) : null}
        </div>
      ) : null}

      {prose ? (
        <div className="flex flex-col gap-3 text-sm leading-7 text-[#1c1915]">
          {blocksOf(prose).map((block, index) =>
            block.type === "ul" ? (
              <ul key={`list-${index}`} className="flex list-disc flex-col gap-1 pl-5">
                {block.items.map((item) => (
                  <li key={item}>
                    <LinkedText text={item} papers={papers} onOpenPaper={onOpenPaper} />
                  </li>
                ))}
              </ul>
            ) : (
              <p key={`p-${index}`}>
                <LinkedText text={block.text} papers={papers} onOpenPaper={onOpenPaper} />
              </p>
            ),
          )}
        </div>
      ) : null}

      {showBrief ? (
        <Brief
          groups={groups}
          titles={named}
          conferenceId={conferenceId}
          pageAction={pageAction}
          activeQuoteId={activeQuoteId}
          activeJobId={activeJobId}
          onOpenQuote={onOpenQuote}
          onOpenPaper={onOpenPaper}
        />
      ) : null}

      {formula ? (
        <section>
          <h3 className="font-[family-name:var(--desk-serif)] text-xl leading-tight text-[#1c1915]">Formula</h3>
          <p className="mt-2 font-[family-name:var(--desk-serif)] text-sm leading-7 text-[#1c1915]">{formula}</p>
        </section>
      ) : null}
    </div>
  );
}
