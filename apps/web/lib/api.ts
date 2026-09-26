export type Product = "stormcite" | "landfall" | "arxaudit";

export type Patch = {
  id: string;
  product: Product;
  kind: "query_template" | "prompt_rule" | "span_window" | "retry_guard_block";
  target: string;
  trigger: string;
  body: string;
  patch_text: string;
  status: "draft" | "live" | "archived";
  wins: number;
  losses: number;
  fitness_ema: number;
  uses: number;
};

export type Claim = {
  id: string;
  text: string;
  type: string;
  evidence_span: string;
  source_id: string;
  source_kind: string;
};

export type TestResult = {
  name: string;
  status: "passed" | "failed" | "not_run";
  log_excerpt: string;
  where: "kaggle" | "local";
};

export type JevVerdict = {
  claim_id: string;
  label: "supported" | "contradicted" | "not_mentioned";
  confidence: number;
  probs: Record<string, number>;
};

export type Budget = {
  jev_calls: number;
  rounds: number;
};

export type Run = {
  run_id: string;
  product: Product;
  goal: string;
  goal_hash: string;
  replay_of: string | null;
  round: number;
  fitness: number;
  final_status: "passed" | "contradicted" | "unresolved";
  claims: Claim[];
  tests: TestResult[];
  jev: JevVerdict[];
  playbook_loaded: Patch[];
  playbook_patches: Patch[];
  budget: Budget;
};

function baseUrl(): string {
  return process.env.ORCHESTRATOR_URL ?? "http://127.0.0.1:8000";
}

function assertServerOnly(): void {
  if (typeof window !== "undefined") {
    throw new Error("Orchestrator API helpers must only run on the server");
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${baseUrl()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    throw new Error(`Orchestrator request failed with status ${res.status}`);
  }
  return (await res.json()) as T;
}

export async function createRun(input: {
  product: Product;
  goal: string;
  fixture?: boolean;
}): Promise<Run> {
  assertServerOnly();
  return requestJson<Run>("/runs", {
    method: "POST",
    body: JSON.stringify({
      product: input.product,
      goal: input.goal,
      fixture: input.fixture ?? false,
    }),
  });
}

export async function getRun(id: string): Promise<Run> {
  assertServerOnly();
  return requestJson<Run>(`/runs/${id}`);
}

export async function replayRun(id: string): Promise<Run> {
  assertServerOnly();
  return requestJson<Run>(`/runs/${id}/replay`, { method: "POST" });
}

export async function getPlaybook(product: Product): Promise<Patch[]> {
  assertServerOnly();
  return requestJson<Patch[]>(
    `/playbook?product=${encodeURIComponent(product)}`,
  );
}

export type BatchKind = "links" | "batch";

export type CreateBatchInput = {
  product: "arxaudit";
  kind: BatchKind;
  name: string | null;
  arxiv_ids: string[];
};

export type Batch = {
  batch_id: string;
  kind: BatchKind;
  name: string | null;
  arxiv_ids: string[];
  created_at: string;
};

export type PaperJob = {
  job_id: string;
  batch_id: string;
  arxiv_id: string;
  run_id: string | null;
  status: string;
  specialist: string | null;
  fitness: number | null;
  issue_count: number;
  author_name: string | null;
  author_email: string | null;
  contacted_at: string | null;
};

export type JobEvent = {
  event_id: string;
  job_id: string;
  specialist: string;
  state: "started" | "finished" | "failed";
  detail: string;
  created_at: string;
};

export type BatchDetail = {
  batch: Batch;
  jobs: PaperJob[];
  events: JobEvent[];
  claims?: Claim[];
};

export async function createBatch(
  input: CreateBatchInput,
): Promise<BatchDetail> {
  assertServerOnly();
  return requestJson<BatchDetail>("/batches", {
    method: "POST",
    body: JSON.stringify({
      product: input.product,
      kind: input.kind,
      name: input.name,
      arxiv_ids: input.arxiv_ids,
    }),
  });
}

export async function getBatch(id: string): Promise<BatchDetail> {
  assertServerOnly();
  return requestJson<BatchDetail>(`/batches/${id}`);
}
