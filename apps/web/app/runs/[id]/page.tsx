import { getRun } from "@/lib/api";
import type { Run } from "@/lib/api";
import { RunPoll } from "./poll";

async function fetchRun(id: string): Promise<Run> {
  "use server";
  return getRun(id);
}

export default async function RunPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let run: Run | null = null;
  let loadError: string | null = null;
  try {
    run = await getRun(id);
  } catch (err) {
    loadError =
      err instanceof Error ? err.message : "Failed to load run.";
  }

  return (
    <main className="mx-auto flex w-full max-w-lg flex-1 flex-col px-6 py-16">
      <h1 className="mb-8 text-2xl font-semibold tracking-tight text-zinc-900">
        Run
      </h1>

      {id ? (
        <RunPoll
          id={id}
          initialRun={run}
          initialError={loadError}
          fetchRun={fetchRun}
        />
      ) : loadError ? (
        <p
          role="alert"
          className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
        >
          {loadError}
        </p>
      ) : null}
    </main>
  );
}
