import { EMPTY_SUMMARY, type Claim, type Paper, type Summary } from "./desk";

const FAILURE_ORDER = ["citation", "number", "table", "support", "semantic", "dataset", "test"] as const;

const FAILURE_LABEL: Record<string, string> = {
  citation: "Citation",
  number: "Number",
  table: "Table",
  support: "Support",
  semantic: "Evidence",
  dataset: "Dataset",
  test: "Rerun",
};

const CLAIM_TYPE_FAILURE: Record<string, string> = {
  citation: "Citation",
  numerical: "Number",
  numerical_comparison: "Table",
  dataset: "Rerun",
  semantic: "Evidence",
};

const FINDING_VERDICTS = new Set(["contradicted", "unresolved", "could_not_reproduce", "insufficient_evidence"]);

export function isFinding(claim: Pick<Claim, "verdict" | "claim_type" | "confidence">): boolean {
  if (FINDING_VERDICTS.has(claim.verdict)) return true;
  return claim.verdict === "not_mentioned" && claim.claim_type === "semantic" && (claim.confidence ?? 0) >= 0.7;
}

export function findings(paper: Pick<Paper, "claims">): Claim[] {
  return (paper.claims ?? []).filter(isFinding);
}

export function findingCount(paper: Pick<Paper, "claims" | "finding_count" | "issues">): number {
  if (typeof paper.finding_count === "number") return paper.finding_count;
  const found = findings(paper);
  if (found.length > 0 || (paper.claims ?? []).length > 0) return found.length;
  return paper.issues?.length ?? 0;
}

export function failureWhere(
  issues: { issue_type: string }[],
  claims: Pick<Claim, "verdict" | "claim_type" | "confidence">[] = [],
): string {
  const ordered: string[] = [];
  const present = new Set(issues.map((issue) => issue.issue_type));
  for (const kind of FAILURE_ORDER) {
    if (present.has(kind)) ordered.push(FAILURE_LABEL[kind]);
  }
  for (const issue of issues) {
    if (!FAILURE_LABEL[issue.issue_type] && !ordered.includes(issue.issue_type)) {
      ordered.push(issue.issue_type);
    }
  }
  for (const claim of claims) {
    if (!isFinding(claim)) continue;
    const label = CLAIM_TYPE_FAILURE[claim.claim_type] ?? claim.claim_type;
    if (!ordered.includes(label)) ordered.push(label);
  }
  return ordered.join(", ");
}

export function findingSentence(issues: { issue_type: string; reason: string }[]): string {
  const reasons: string[] = [];
  const seen = new Set<string>();
  for (const issue of issues) {
    if (issue.issue_type === "ai_likeness") continue;
    let reason = issue.reason.replace(/\s+/g, " ").trim();
    if (!reason) continue;
    if (!reason.endsWith(".")) reason = `${reason}.`;
    const key = reason.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    reasons.push(reason);
  }
  return reasons.join(" ");
}

export function verdictLabel(status: string, count?: number): string {
  if (status === "passed") return "Verified";
  if (status === "contradicted") {
    if (typeof count !== "number" || count <= 0) return "Findings";
    return count === 1 ? "1 finding" : `${count} findings`;
  }
  if (status === "error") return "Not read";
  if (status === "queued") return "Waiting";
  if (status === "running") return "Running";
  return "Not judged yet";
}

export function paperLabel(paper: Pick<Paper, "status" | "claims" | "finding_count" | "issues">): string {
  return verdictLabel(paper.status, findingCount(paper));
}

export function verdictTone(status: string): string {
  if (status === "passed") return "text-[#2f6b4f]";
  if (status === "contradicted" || status === "error") return "text-[#8c3a2f]";
  if (status === "running") return "text-[#8a6a2f]";
  return "text-[#6b645c]";
}

const CLAIM_WORD: Record<string, string> = {
  supported: "Supported",
  contradicted: "Contradicted",
  not_mentioned: "Not found",
  unresolved: "Unresolved",
  ambiguous: "Ambiguous",
  reproduced: "Reproduced",
  could_not_reproduce: "Could not reproduce",
  insufficient_evidence: "Insufficient evidence",
  not_checked: "Not checked",
};

export function claimVerdictLabel(verdict: string): string {
  return CLAIM_WORD[verdict] ?? verdict;
}

export function claimVerdictNote(verdict: string): string {
  return verdict === "insufficient_evidence" ? "Requires human review" : "";
}

export function claimVerdictTone(claim: Pick<Claim, "verdict" | "claim_type" | "confidence">): string {
  if (isFinding(claim)) return "text-[#8c3a2f]";
  if (claim.verdict === "supported" || claim.verdict === "reproduced") return "text-[#2f6b4f]";
  return "text-[#6b645c]";
}

const DEPTH_WORD: Record<string, string> = {
  consistency: "Consistency",
  external: "External",
  mathematical: "Mathematical",
  computational: "Computational",
  evidence: "Evidence",
};

export function depthLabel(depth: string): string {
  return DEPTH_WORD[depth] ?? depth;
}

const TYPE_WORD: Record<string, string> = {
  citation: "Citation",
  numerical: "Number",
  numerical_comparison: "Comparison",
  dataset: "Dataset",
  semantic: "Claim",
};

export function claimTypeLabel(kind: string): string {
  return TYPE_WORD[kind] ?? kind;
}

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

export function summaryOf(paper: Pick<Paper, "summary">): Summary {
  return paper.summary ?? EMPTY_SUMMARY;
}

export function summaryLine(summary: Summary): string {
  if (!summary || summary.analyzed === 0) return "";
  const parts = [plural(summary.analyzed, "claim analyzed", "claims analyzed"), `${summary.supported} supported`];
  if (summary.contradicted) parts.push(`${summary.contradicted} contradicted`);
  if (summary.unresolved) parts.push(plural(summary.unresolved, "unresolved citation", "unresolved citations"));
  if (summary.not_reproduced) parts.push(`${summary.not_reproduced} not reproduced`);
  if (summary.insufficient) parts.push(plural(summary.insufficient, "needs human review", "need human review"));
  return parts.join(" · ");
}

export function categoryLines(summary: Summary): { label: string; value: string; total: number }[] {
  const c = summary.categories;
  return [
    { label: "Citations resolved", value: `${c.citations.resolved} / ${c.citations.total}`, total: c.citations.total },
    { label: "Internal consistency", value: `${c.internal.supported} / ${c.internal.total}`, total: c.internal.total },
    { label: "Numerical consistency", value: `${c.numerical.consistent} / ${c.numerical.total}`, total: c.numerical.total },
    {
      label: "Computational reproduction",
      value: `${c.computational.reproduced} / ${c.computational.total}`,
      total: c.computational.total,
    },
  ];
}

export function percent(confidence: number): string {
  return `${Math.round((confidence ?? 0) * 100)}%`;
}
