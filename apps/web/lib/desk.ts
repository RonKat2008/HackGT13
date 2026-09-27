const base = process.env.ORCHESTRATOR_URL ?? "http://127.0.0.1:8000";

export async function deskFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    throw new Error(`Desk request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export async function deskRaw(path: string): Promise<Response> {
  return fetch(`${base}${path}`, { cache: "no-store" });
}

export type ConferenceSummary = {
  conference_id: string;
  name: string;
  contact_email: string;
  queued: number;
  running: number;
  finished: number;
};

export type Issue = {
  issue_type: string;
  claim_text: string;
  evidence_span: string;
  jev_label: string;
  reason: string;
  page?: number | null;
};

export type Quote = {
  quote_id: string;
  job_id: string;
  arxiv_id: string;
  title: string;
  page: number | null;
  text: string;
  issue_type: string;
  reason: string;
};

export type TraceStep = {
  id: string;
  kind: "choose" | "verdict" | "quote";
  label: string;
  detail: string;
  quote_id: string | null;
};

export type JobEvent = {
  specialist: string;
  state: string;
  detail: string;
};

export type ShelfNeighbor = {
  title: string;
  label: string;
  excerpt: string;
  cosine: number;
};

export type KaggleRun = {
  where: string;
  status: string;
  log: string;
  kernel_url: string | null;
  detail: string;
  code?: string;
  claim_text?: string;
};

export type ClaimType = "citation" | "numerical" | "numerical_comparison" | "dataset" | "semantic";

export type ClaimVerdict =
  | "supported"
  | "contradicted"
  | "not_mentioned"
  | "unresolved"
  | "ambiguous"
  | "reproduced"
  | "could_not_reproduce"
  | "insufficient_evidence"
  | "not_checked";

export type Depth = "consistency" | "external" | "mathematical" | "computational" | "evidence";

export type Evidence = {
  page: number | null;
  section: string;
  text: string;
  role: "supports" | "contradicts" | "context";
  source: "paper" | "catalog" | "dataset" | "computation";
};

export type CatalogQuery = {
  catalog: string;
  status: string;
  candidate_title: string;
  doi: string;
  score: number;
};

export type Catalog = {
  queried: CatalogQuery[];
  reference: string;
};

export type Computation = {
  claim_id: string;
  dataset_slug: string;
  resolution: "match" | "ambiguous" | "not_found" | string;
  spec: Record<string, unknown>;
  actual: number | string | null;
  expected: number | string | null;
  status: "reproduced" | "could_not_reproduce" | "could_not_run" | string;
  steps: string[];
  log: string;
  formula: string;
};

export type Claim = {
  claim_id: string;
  job_id: string;
  text: string;
  page: number | null;
  section: string;
  claim_type: ClaimType | string;
  verdict: ClaimVerdict | string;
  confidence: number;
  depth: Depth | string;
  rounds: number;
  reason: string;
  evidence: Evidence[];
  steps: string[];
  catalog: Catalog | null;
  computation: Computation | null;
};

export type CategoryCount = { total: number; not_checked?: number } & Record<string, number>;

export type Summary = {
  analyzed: number;
  supported: number;
  contradicted: number;
  unresolved: number;
  not_reproduced: number;
  insufficient: number;
  not_checked?: number;
  categories: {
    citations: { resolved: number; total: number; not_checked?: number };
    internal: { supported: number; total: number; not_checked?: number };
    numerical: { consistent: number; total: number; not_checked?: number };
    computational: { reproduced: number; total: number; not_checked?: number };
  };
};

export const EXAMPLE_JOB_ID = "example-0000-00003";

export const EMPTY_SUMMARY: Summary = {
  analyzed: 0,
  supported: 0,
  contradicted: 0,
  unresolved: 0,
  not_reproduced: 0,
  insufficient: 0,
  not_checked: 0,
  categories: {
    citations: { resolved: 0, total: 0, not_checked: 0 },
    internal: { supported: 0, total: 0, not_checked: 0 },
    numerical: { consistent: 0, total: 0, not_checked: 0 },
    computational: { reproduced: 0, total: 0, not_checked: 0 },
  },
};

export type Paper = {
  job_id: string;
  arxiv_id: string;
  title: string;
  abstract: string;
  status: string;
  specialist: string | null;
  author_name: string | null;
  issue_count: number;
  finding_count?: number;
  paper_text: string;
  sections: Record<string, string>;
  issues: Issue[];
  claims?: Claim[];
  summary?: Summary;
  events: JobEvent[];
  neighbors?: ShelfNeighbor[];
  kaggle?: KaggleRun | null;
};

export type ConferenceDesk = {
  conference_id: string;
  name: string;
  contact_email: string;
  running: boolean;
  papers: Paper[];
};
