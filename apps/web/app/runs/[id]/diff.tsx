import type { Run } from "@/lib/api";

export function RoundDiff({ run }: { run: Run }) {
  const jevByClaimId = new Map(run.jev.map((v) => [v.claim_id, v]));
  const patches = run.playbook_patches;

  return (
    <section className="mt-10">
      <h2 className="mb-4 text-lg font-semibold tracking-tight text-zinc-900">
        Round patch and current Jev labels
      </h2>

      {patches.length === 0 ? (
        <p className="text-sm text-zinc-600">No patch yet.</p>
      ) : (
        <ul className="mb-8 flex flex-col gap-4 text-sm">
          {patches.map((patch) => (
            <li
              key={patch.id}
              className="border-b border-zinc-100 pb-4 last:border-b-0"
            >
              <p className="font-medium text-zinc-700">
                Kind:{" "}
                <span className="font-normal text-zinc-900">{patch.kind}</span>
              </p>
              <p className="mt-1 text-zinc-700">
                Body:{" "}
                <span className="font-normal text-zinc-900">{patch.body}</span>
              </p>
            </li>
          ))}
        </ul>
      )}

      <h3 className="mb-3 text-sm font-medium text-zinc-700">
        Current Jev labels
      </h3>
      {run.claims.length === 0 ? (
        <p className="text-sm text-zinc-600">No claims yet.</p>
      ) : (
        <ul className="flex flex-col gap-3 text-sm">
          {run.claims.map((claim) => {
            const verdict = jevByClaimId.get(claim.id);
            return (
              <li key={claim.id} className="text-zinc-900">
                <span className="text-zinc-700">{claim.text}</span>
                {" — "}
                <span className="font-medium">
                  {verdict?.label ?? "no label"}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
