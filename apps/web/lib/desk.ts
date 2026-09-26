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

export type Paper = {
  job_id: string;
  arxiv_id: string;
  title: string;
  abstract: string;
  status: string;
  specialist: string | null;
  author_name: string | null;
  issue_count: number;
  paper_text: string;
  sections: Record<string, string>;
  issues: Issue[];
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
