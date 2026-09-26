import { readFileSync } from "node:fs";
import path from "node:path";
import { EXAMPLE_JOB_ID, type Paper } from "./desk";

function fixturePath(): string {
  const name = "desk_paper_example.json";
  const roots = [
    path.join(process.cwd(), "..", "..", "services", "orchestrator", "fixtures", name),
    path.join(process.cwd(), "services", "orchestrator", "fixtures", name),
  ];
  for (const candidate of roots) {
    try {
      readFileSync(candidate, "utf8");
      return candidate;
    } catch {
      continue;
    }
  }
  return roots[0];
}

export function examplePaper(): Paper {
  const paper = JSON.parse(readFileSync(fixturePath(), "utf8")) as Paper;
  paper.job_id = EXAMPLE_JOB_ID;
  paper.events = paper.events ?? [];
  paper.issues = paper.issues ?? [];
  paper.claims = paper.claims ?? [];
  return paper;
}

export function withExample(papers: Paper[]): Paper[] {
  const sample = examplePaper();
  if (papers.some((paper) => paper.job_id === sample.job_id)) return papers;
  return [sample, ...papers];
}
