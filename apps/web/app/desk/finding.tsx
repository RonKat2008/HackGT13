"use client";

import type { Claim, Computation } from "@/lib/desk";
import {
  claimVerdictLabel,
  claimVerdictNote,
  claimVerdictTone,
  depthLabel,
  isFinding,
  percent,
} from "@/lib/verdict";

const CATALOG_NAME: Record<string, string> = {
  crossref: "Crossref",
  openalex: "OpenAlex",
  semantic_scholar: "Semantic Scholar",
};

export function evidencePage(claim: Claim): number | null {
  const contradicting = claim.evidence.find((item) => item.role === "contradicts" && item.page);
  return contradicting?.page ?? claim.evidence.find((item) => item.page)?.page ?? claim.page;
}

export function catalogWord(status: string): string {
  const value = status.toLowerCase();
  if (value === "match" || value === "resolved" || value === "supported") return "Match";
  if (value === "error" || value === "not_checked") return "Not checked";
  return "No match";
}

function specLine(computation: Computation): string {
  const spec = computation.spec ?? {};
  const operation = String(spec.operation ?? spec.op ?? "");
  const column = spec.column ? String(spec.column) : "";
  const equals = spec.equals ?? spec.value;
  if (operation && column && equals != null) return `${operation}(${column}, ${equals})`;
  if (operation && column) return `${operation}(${column})`;
  if (computation.formula) return computation.formula;
  return operation;
}

export function FindingCard({
  claim,
  onViewEvidence,
}: {
  claim: Claim;
  onViewEvidence?: (page: number | null) => void;
}) {
  const evidence = claim.evidence.find((item) => item.role === "contradicts") ?? claim.evidence[0];
  const note = claimVerdictNote(claim.verdict);
  const page = evidencePage(claim);

  return (
    <article className="rounded-2xl bg-white px-3 py-3 ring-1 ring-[#e4dcd0]">
      <p className="text-[11px] tracking-[0.12em] text-[#6b645c]">Claim{claim.page ? ` — Page ${claim.page}` : ""}</p>
      <blockquote className="mt-1 font-[family-name:var(--desk-serif)] text-sm leading-6">{claim.text}</blockquote>
      {evidence?.text ? (
        <>
          <p className="mt-3 text-[11px] tracking-[0.12em] text-[#6b645c]">
            Evidence{evidence.page ? ` — Page ${evidence.page}` : ""}
          </p>
          <blockquote className="mt-1 text-sm leading-6 text-[#1c1915]">{evidence.text}</blockquote>
        </>
      ) : null}
      <p className={`mt-3 text-sm font-semibold ${claimVerdictTone(claim)}`}>
        {claimVerdictLabel(claim.verdict)}
        {note ? ` · ${note}` : ""}
      </p>
      <p className="mt-1 text-xs text-[#6b645c]">
        {percent(claim.confidence)} · {depthLabel(claim.depth)}
      </p>
      {claim.steps.length > 0 ? (
        <ul className="mt-3 flex flex-col gap-1 text-xs leading-5 text-[#1c1915]">
          {claim.steps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ul>
      ) : null}
      {claim.catalog && claim.catalog.queried.length > 0 ? (
        <ul className="mt-3 flex flex-col gap-1 text-xs">
          {claim.catalog.queried.map((row) => (
            <li key={row.catalog} className="flex justify-between gap-3">
              <span>{CATALOG_NAME[row.catalog] ?? row.catalog}</span>
              <span className="text-[#6b645c]">{catalogWord(row.status)}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {claim.computation ? (
        <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
          <dt className="text-[#6b645c]">Spec</dt>
          <dd>{specLine(claim.computation)}</dd>
          <dt className="text-[#6b645c]">Expected</dt>
          <dd>{claim.computation.expected ?? "—"}</dd>
          <dt className="text-[#6b645c]">Actual</dt>
          <dd>{claim.computation.actual ?? "—"}</dd>
          <dt className="text-[#6b645c]">Formula</dt>
          <dd>{claim.computation.formula || "—"}</dd>
        </dl>
      ) : null}
      {onViewEvidence ? (
        <button
          type="button"
          className="mt-3 text-xs underline decoration-[#c4a15a] underline-offset-4"
          onClick={() => onViewEvidence(page)}
        >
          View evidence in PDF
        </button>
      ) : null}
      {isFinding(claim) && claim.reason ? <p className="mt-2 text-xs leading-5 text-[#6b645c]">{claim.reason}</p> : null}
    </article>
  );
}
