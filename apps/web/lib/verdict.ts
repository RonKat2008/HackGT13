const FAILURE_ORDER = ["citation", "number", "support", "dataset", "test"] as const;

const FAILURE_LABEL: Record<string, string> = {
  citation: "Citation",
  number: "Number",
  support: "Support",
  dataset: "Dataset",
  test: "Rerun",
};

export function failureWhere(issues: { issue_type: string }[]): string {
  const present = new Set(issues.map((issue) => issue.issue_type));
  const ordered = FAILURE_ORDER.filter((kind) => present.has(kind)).map((kind) => FAILURE_LABEL[kind]);
  for (const issue of issues) {
    if (!FAILURE_LABEL[issue.issue_type] && !ordered.includes(issue.issue_type)) {
      ordered.push(issue.issue_type);
    }
  }
  return ordered.join(", ");
}

export function verdictLabel(status: string): string {
  if (status === "passed") return "Passed";
  if (status === "contradicted") return "Failed";
  if (status === "error") return "Not read";
  if (status === "queued") return "Waiting";
  if (status === "running") return "Running";
  return "Not judged yet";
}

export function verdictTone(status: string): string {
  if (status === "passed") return "text-[#2f6b4f]";
  if (status === "contradicted" || status === "error") return "text-[#8c3a2f]";
  if (status === "running") return "text-[#8a6a2f]";
  return "text-[#6b645c]";
}
