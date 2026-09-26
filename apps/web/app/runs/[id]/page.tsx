import { getRun } from "@/lib/api";
import { Claims } from "./claims";

export default async function RunPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let run;
  try {
    run = await getRun(id);
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Failed to load run.";
    return (
      <main className="mx-auto flex w-full max-w-lg flex-1 flex-col px-6 py-16">
        <h1 className="mb-4 text-2xl font-semibold tracking-tight text-zinc-900">
          Run
        </h1>
        <p
          role="alert"
          className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
        >
          {message}
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto flex w-full max-w-lg flex-1 flex-col px-6 py-16">
      <h1 className="mb-8 text-2xl font-semibold tracking-tight text-zinc-900">
        Run
      </h1>

      <dl className="flex flex-col gap-4 text-sm">
        <div>
          <dt className="font-medium text-zinc-700">Goal</dt>
          <dd className="mt-1 text-zinc-900">{run.goal}</dd>
        </div>

        <div>
          <dt className="font-medium text-zinc-700">Product</dt>
          <dd className="mt-1 text-zinc-900">{run.product}</dd>
        </div>

        <div>
          <dt className="font-medium text-zinc-700">Final status</dt>
          <dd className="mt-1 text-zinc-900">{run.final_status}</dd>
        </div>

        <div>
          <dt className="font-medium text-zinc-700">Fitness</dt>
          <dd className="mt-1 text-zinc-900">{run.fitness}</dd>
        </div>

        {typeof run.replay_of === "string" ? (
          <div>
            <dt className="font-medium text-zinc-700">Replay of</dt>
            <dd className="mt-1 text-zinc-900">{run.replay_of}</dd>
          </div>
        ) : null}
      </dl>

      <Claims run={run} />
    </main>
  );
}
