import type { Run } from "@/lib/api";

export function Claims({ run }: { run: Run }) {
  const rowCount = Math.max(run.claims.length, run.tests.length);
  const jevByClaimId = new Map(run.jev.map((v) => [v.claim_id, v]));

  const rows = Array.from({ length: rowCount }, (_, i) => {
    const claim = run.claims[i];
    const test = run.tests[i];
    const verdict = claim ? jevByClaimId.get(claim.id) : undefined;
    return { claim, test, verdict };
  });

  return (
    <div className="mt-10 overflow-x-auto">
      <table className="w-full border-collapse text-left text-sm">
        <thead>
          <tr className="border-b border-zinc-200 text-zinc-700">
            <th className="px-2 py-2 font-medium">Claim</th>
            <th className="px-2 py-2 font-medium">Span</th>
            <th className="px-2 py-2 font-medium">Jev label</th>
            <th className="px-2 py-2 font-medium">Confidence</th>
            <th className="px-2 py-2 font-medium">Test status</th>
            <th className="px-2 py-2 font-medium">Where</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ claim, test, verdict }, i) => (
            <tr key={claim?.id ?? `test-${i}`} className="border-b border-zinc-100">
              <td className="px-2 py-2 text-zinc-900">{claim?.text ?? ""}</td>
              <td className="px-2 py-2 text-zinc-900">
                {claim?.evidence_span ?? ""}
              </td>
              <td className="px-2 py-2 text-zinc-900">{verdict?.label ?? ""}</td>
              <td className="px-2 py-2 text-zinc-900">
                {verdict != null ? verdict.confidence : ""}
              </td>
              <td className="px-2 py-2 text-zinc-900">{test?.status ?? ""}</td>
              <td className="px-2 py-2 text-zinc-900">{test?.where ?? ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
