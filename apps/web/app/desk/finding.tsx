"use client";

import { useState } from "react";
import type { Claim, Computation } from "@/lib/desk";
import {
  claimVerdictLabel,
  claimVerdictNote,
  claimVerdictTone,
  depthLabel,
  isFinding,
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
  const evidence = claim.evidence.find((item) => item.role === "contradicts") ?? claim.evidence[0];
  const note = claimVerdictNote(claim.verdict);
  const page = evidencePage(claim);
  const [chain, setChain] = useState(false);

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
      <button
        type="button"
        aria-expanded={chain}
        onClick={() => setChain((open) => !open)}
        className="mt-3 text-[11px] tracking-[0.12em] text-[#6b645c]"
      >
        Chain
      </button>
      {chain ? <Provenance claim={claim} /> : null}
      {claim.steps.length > 0 ? (
        <ul className="mt-3 flex flex-col gap-1 text-xs leading-5 text-[#1c1915]">
          {claim.steps.map((step, index) => {
            const actor = judgeActor(step);
            return (
              <li key={`${index}-${step}`} className="flex items-baseline gap-2">
                {actor ? (
                  <span className="shrink-0 text-[11px] tracking-[0.12em] text-[#8a6a2f]">{actor}</span>
                ) : null}
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
        <div className="mt-3 flex flex-wrap gap-1.5">
          {claim.evidence
            .filter((item) => item.text.trim() && !item.text.startsWith("Neighbor window"))
            .slice(0, 4)
            .map((item, index) => (
              <button
                key={`${item.role}-${item.page ?? 0}-${index}`}
                type="button"
                className="rounded-full px-2 py-1 text-[11px] text-[#1c1915] ring-1 ring-[#e4dcd0]"
                onClick={() => onViewEvidence(item.page, item.text)}
              >
                {item.role}
                {item.page ? ` p.${item.page}` : ""}
              </button>
            ))}
          <button
            type="button"
            className="text-xs underline decoration-[#c4a15a] underline-offset-4"
            onClick={() => onViewEvidence(page, evidence?.text || claim.text)}
          >
            View evidence in PDF
          </button>
        </div>
      ) : null}
      {isFinding(claim) && claim.reason ? <p className="mt-2 text-xs leading-5 text-[#6b645c]">{claim.reason}</p> : null}
    </article>
  );
}
