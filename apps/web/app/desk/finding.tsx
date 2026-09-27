"use client";

import { useState } from "react";
import type { Claim, Computation } from "@/lib/desk";
import {
  claimVerdictLabel,
  claimVerdictNote,
  claimVerdictTone,
  depthLabel,
  percent,
} from "@/lib/verdict";
import { Provenance } from "./provenance";

const CATALOG_NAME: Record<string, string> = {
  crossref: "Crossref",
  openalex: "OpenAlex",
  semantic_scholar: "Semantic Scholar",
};

export function evidencePage(claim: Claim): number | null {
  const contradicting = claim.evidence.find((item) => item.role === "contradicts" && item.page);
  return contradicting?.page ?? claim.evidence.find((item) => item.page)?.page ?? claim.page;
}

export function judgeActor(step: string): "Lya" | "Jev" | null {
  if (step.startsWith("Lya")) return "Lya";
  if (step.startsWith("Jev")) return "Jev";
  return null;
}

export function stepBody(step: string, actor: "Lya" | "Jev" | null): string {
  if (!actor) return step;
  const rest = step.slice(actor.length).trim();
  return rest || step;
}

export function catalogWord(status: string): string {
  const value = status.toLowerCase();
  if (value === "match" || value === "resolved" || value === "supported") return "Match";
  if (value === "error" || value === "not_checked") return "Not checked";
  return "No match";
}

export function reviewKind(claim: Claim): string {
  if (claim.claim_type === "numerical") return "Number";
  if (claim.claim_type === "numerical_comparison") return "Table";
  if (claim.claim_type === "dataset") return "Count";
  if (claim.claim_type === "citation") return "Citation";
  return "Sentence";
}

export function reviewResult(claim: Claim): string {
  const reason = claim.reason.replace(/\s+/g, " ").trim().replace(/\.$/, "");
  const verdict = claimVerdictLabel(claim.verdict);
  const terseCount = /^computed\s+\S+,?\s+claimed\s+\S+$/i.test(reason);
  if (reason && reason.toLowerCase() !== verdict.toLowerCase() && !terseCount) {
    return `${reason}.`;
  }
  if (claim.computation?.actual != null && claim.computation.expected != null) {
    return `Counted ${claim.computation.actual}. The paper says ${claim.computation.expected}.`;
  }
  if (claim.verdict === "reproduced") return "This matches the public table.";
  if (claim.verdict === "supported") return "Nothing in the paper disagrees with this.";
  if (claim.verdict === "insufficient_evidence") return "A person still has to decide.";
  if (claim.verdict === "could_not_reproduce") return "The public table does not match this count.";
  if (claim.verdict === "contradicted") return "This does not match the rest of the paper.";
  if (claim.verdict === "not_checked") return "This was not checked.";
  return verdict;
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
  onViewEvidence?: (page: number | null, text?: string) => void;
}) {
  const against =
    claim.evidence.find((item) => item.role === "contradicts" && item.text.trim()) ??
    claim.evidence.find((item) => item.text.trim() && item.text !== claim.text && !item.text.startsWith("Neighbor window"));
  const page = evidencePage(claim);
  const [checked, setChecked] = useState(false);
  const note = claimVerdictNote(claim.verdict);
  const counted =
    claim.computation && claim.computation.actual != null
      ? `Counted ${claim.computation.actual}${claim.computation.formula ? `. ${claim.computation.formula}` : ""}`
      : "";

  return (
    <article className="rounded-2xl bg-white px-3 py-3 ring-1 ring-[#c4a15a]">
      <p className="text-xs text-[#6b645c]">
        {reviewKind(claim)}
        {claim.page ? ` · page ${claim.page}` : ""}
      </p>
      <p className="mt-2 text-xs text-[#6b645c]">The paper says</p>
      <blockquote className="mt-1 font-[family-name:var(--desk-serif)] text-sm leading-6 text-[#1c1915]">
        {claim.text}
      </blockquote>
      {against?.text ? (
        <>
          <p className="mt-3 text-xs text-[#6b645c]">
            {against.page ? `Elsewhere in the paper, page ${against.page}` : "Elsewhere in the paper"}
          </p>
          <blockquote className="mt-1 text-sm leading-6 text-[#1c1915]">{against.text}</blockquote>
        </>
      ) : null}
      {counted ? <p className="mt-3 text-sm leading-6 text-[#1c1915]">{counted}</p> : null}
      <p className={`mt-3 text-sm leading-6 ${claimVerdictTone(claim)}`}>{reviewResult(claim)}</p>
      {note ? <p className="mt-1 text-xs text-[#8a6a2f]">{note}</p> : null}
      {onViewEvidence ? (
        <button
          type="button"
          className="mt-3 text-sm text-[#1c1915] underline decoration-[#c4a15a] underline-offset-4"
          onClick={() => onViewEvidence(against?.page ?? page, against?.text || claim.text)}
        >
          Show in the PDF
        </button>
      ) : null}
      <button
        type="button"
        aria-expanded={checked}
        onClick={() => setChecked((open) => !open)}
        className="mt-3 block text-xs text-[#6b645c]"
      >
        {checked ? "Hide how this was checked" : "How this was checked"}
      </button>
      {checked ? (
        <div className="mt-3 border-t border-[#e4dcd0] pt-3">
          <p className="text-xs text-[#6b645c]">
            {claimVerdictLabel(claim.verdict)} · {percent(claim.confidence)} · {depthLabel(claim.depth)}
          </p>
          <Provenance claim={claim} />
          {claim.steps.length > 0 ? (
            <ul className="mt-3 flex flex-col gap-1 text-xs leading-5 text-[#1c1915]">
              {claim.steps.map((step, index) => {
                const actor = judgeActor(step);
                return (
                  <li key={`${index}-${step}`} className="flex items-baseline gap-2">
                    {actor ? <span className="shrink-0 text-[#8a6a2f]">{actor}</span> : null}
                    <span>{stepBody(step, actor)}</span>
                  </li>
                );
              })}
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
              <dt className="text-[#6b645c]">Check</dt>
              <dd>{specLine(claim.computation) || "—"}</dd>
              <dt className="text-[#6b645c]">Paper</dt>
              <dd>{claim.computation.expected ?? "—"}</dd>
              <dt className="text-[#6b645c]">Counted</dt>
              <dd>{claim.computation.actual ?? "—"}</dd>
            </dl>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
