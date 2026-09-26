import review from "./fixtures/review.json";
import { AuditStart } from "./start";

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
      <AuditStart
        jobs={jobs}
        issue={issue}
        neighbors={neighbors}
        runningSpecialist={runningJob ? runningJob.specialist : "None"}
      />
    </main>
  );
}
