import { redirect } from "next/navigation";
import { getRun, replayRun } from "@/lib/api";
import type { Run } from "@/lib/api";
import { RunPoll } from "./poll";

async function fetchRun(id: string): Promise<Run> {
  "use server";
  return getRun(id);
}

async function replayWithPlaybook(formData: FormData) {
  "use server";

  const id = String(formData.get("id") ?? "").trim();
  if (!id) {
    redirect(`/runs/?error=${encodeURIComponent("Run id is required.")}`);
  }

  let newRun: Run;
  try {
    newRun = await replayRun(id);
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Failed to replay run.";
    redirect(`/runs/${id}?error=${encodeURIComponent(message)}`);
  }
  redirect(`/runs/${newRun.run_id}`);
}

export default async function RunPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ error?: string | string[] }>;
}) {
  const { id } = await params;
  const sp = await searchParams;
  const rawError = sp.error;
  const replayError =
    typeof rawError === "string"
      ? rawError
      : Array.isArray(rawError)
        ? rawError[0]
        : undefined;

  let run: Run | null = null;
  let loadError: string | null = null;
  try {
    run = await getRun(id);
  } catch (err) {
    loadError =
      err instanceof Error ? err.message : "Failed to load run.";
  }

  let parentRun: Run | null = null;
  let parentError: string | null = null;
  if (typeof run?.replay_of === "string") {
    try {
      parentRun = await getRun(run.replay_of);
    } catch (err) {
      parentError =
        err instanceof Error ? err.message : "Failed to load parent run.";
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-lg flex-1 flex-col px-6 py-16">
      <h1 className="mb-8 text-2xl font-semibold tracking-tight text-zinc-900">
        Run
      </h1>

      {replayError ? (
        <p
          role="alert"
          className="mb-6 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
        >
          {replayError}
        </p>
      ) : null}

      {typeof run?.replay_of === "string" ? (
        <section className="mb-6 space-y-2 text-sm text-zinc-900">
          <h2 className="text-base font-medium text-zinc-800">
            Fitness comparison
          </h2>
          <dl className="space-y-2">
            <div>
              <dt className="font-medium text-zinc-700">This run fitness</dt>
              <dd className="mt-1">{run.fitness}</dd>
            </div>
            {parentRun ? (
              <div>
                <dt className="font-medium text-zinc-700">
                  Parent run ({run.replay_of}) fitness
                </dt>
                <dd className="mt-1">{parentRun.fitness}</dd>
              </div>
            ) : null}
          </dl>
          {parentError ? (
            <p
              role="alert"
              className="rounded border border-red-200 bg-red-50 px-3 py-2 text-red-800"
            >
              Parent run: {parentError}
            </p>
          ) : null}
        </section>
      ) : null}

      {run ? (
        <form action={replayWithPlaybook} className="mb-6">
          <input type="hidden" name="id" value={id} />
          <button
            type="submit"
            className="rounded bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 focus:outline-none focus:ring-2 focus:ring-zinc-500 focus:ring-offset-2"
          >
            Replay with playbook
          </button>
        </form>
      ) : null}

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
