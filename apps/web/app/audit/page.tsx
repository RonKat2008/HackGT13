import review from "./fixtures/review.json";

type Job = (typeof review.jobs)[number];
type Issue = (typeof review.issues)[number];
type Neighbor = (typeof review.neighbors)[number];

export default function AuditPage() {
  const jobs = review.jobs as Job[];
  const issues = review.issues as Issue[];
  const neighbors = review.neighbors as Neighbor[];
  const runningJob = jobs.find((job) => job.status === "running");
  const issue = issues[0];

  return (
    <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col px-6 py-10">
      <h1 className="mb-2 text-2xl font-semibold tracking-tight text-zinc-900">
        ArxAudit
      </h1>
      <p className="mb-8 text-sm text-zinc-600">
        Fixture includes {neighbors.length} shelf neighbors.
      </p>

      <div className="grid flex-1 gap-6 md:grid-cols-3">
        <section className="flex flex-col gap-4">
          <h2 className="text-sm font-medium uppercase tracking-wide text-zinc-500">
            Papers
          </h2>
          <ul className="flex flex-col gap-3">
            {jobs.map((job) => (
              <li
                key={job.job_id}
                className="border border-zinc-200 px-3 py-3 text-sm text-zinc-900"
              >
                <p className="font-medium">{job.arxiv_id}</p>
                <p className="mt-1 text-zinc-600">Status: {job.status}</p>
                <p className="text-zinc-600">Specialist: {job.specialist}</p>
                <p className="text-zinc-600">Issues: {job.issue_count}</p>
              </li>
            ))}
          </ul>
        </section>

        <section className="flex flex-col gap-4">
          <h2 className="text-sm font-medium uppercase tracking-wide text-zinc-500">
            Issue
          </h2>
          {issue ? (
            <div className="border border-zinc-200 px-3 py-3 text-sm text-zinc-900">
              <p className="font-medium">Type: {issue.issue_type}</p>
              <p className="mt-2">
                <span className="text-zinc-500">Claim: </span>
                {issue.claim_text}
              </p>
              <p className="mt-2">
                <span className="text-zinc-500">Evidence: </span>
                {issue.evidence_span}
              </p>
              <p className="mt-2">
                <span className="text-zinc-500">Jev label: </span>
                {issue.jev_label}
              </p>
              <p className="mt-2">
                <span className="text-zinc-500">Reason: </span>
                {issue.reason}
              </p>
            </div>
          ) : null}

          <p className="text-sm text-zinc-700">
            Nearest reference abstracts. This is not a verdict.
          </p>
          <ul className="flex flex-col gap-3">
            {neighbors.map((neighbor) => (
              <li
                key={neighbor.title}
                className="border border-zinc-200 px-3 py-3 text-sm text-zinc-900"
              >
                <p className="font-medium">{neighbor.title}</p>
                <p className="mt-1 text-zinc-600">
                  Label: {neighbor.label} · Cosine: {neighbor.cosine.toFixed(2)}
                </p>
              </li>
            ))}
          </ul>
        </section>

        <section className="flex flex-col gap-4">
          <h2 className="text-sm font-medium uppercase tracking-wide text-zinc-500">
            Running
          </h2>
          <p className="border border-zinc-200 px-3 py-3 text-sm text-zinc-900">
            {runningJob ? runningJob.specialist : "None"}
          </p>
        </section>
      </div>
    </main>
  );
}
