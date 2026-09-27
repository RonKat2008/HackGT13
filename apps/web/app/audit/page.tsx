import { existsSync, readFileSync } from "fs";
import path from "path";
import review from "./fixtures/review.json";
import { AuditStart } from "./start";

type Job = (typeof review.jobs)[number];
type Issue = (typeof review.issues)[number];
type Probe = (typeof review.probe);
type TestLog = (typeof review.test_log);

function readDatasetsLinks(): {
  datasetUrl: string | null;
  kernelUrl: string | null;
} {
  const candidates = [
    path.resolve(process.cwd(), "..", "..", "kaggle", "DATASETS.md"),
    path.resolve(process.cwd(), "kaggle", "DATASETS.md"),
  ];
  const datasetsPath = candidates.find((candidate) => existsSync(candidate));
  if (!datasetsPath) {
    return { datasetUrl: null, kernelUrl: null };
  }
  try {
    const text = readFileSync(datasetsPath, "utf8");
    const urls =
      text.match(/https:\/\/www\.kaggle\.com\/[^\s)\]>"']+/g) ?? [];
    let datasetUrl: string | null = null;
    let kernelUrl: string | null = null;
    for (const url of urls) {
      if (!datasetUrl && url.includes("/datasets/")) {
        datasetUrl = url;
      }
      if (!kernelUrl && (url.includes("/code/") || url.includes("/kernels/"))) {
        kernelUrl = url;
      }
    }
    return { datasetUrl, kernelUrl };
  } catch {
    return { datasetUrl: null, kernelUrl: null };
  }
}

export default function AuditPage() {
  const jobs = review.jobs as Job[];
  const issues = review.issues as Issue[];
  const probe = review.probe as Probe;
  const testLog = review.test_log as TestLog;
  const { datasetUrl, kernelUrl } = readDatasetsLinks();

  return (
    <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col px-6 py-10">
      <header className="mb-2 flex flex-wrap items-baseline gap-4">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">
          PreSearch
        </h1>
        <a
          href="/audit/conferences"
          className="text-sm text-zinc-700 underline underline-offset-2"
        >
          Conference dashboard
        </a>
      </header>
      <AuditStart
        jobs={jobs}
        issues={issues}
        probe={probe}
        testLog={testLog}
        datasetUrl={datasetUrl}
        kernelUrl={kernelUrl}
      />
    </main>
  );
}
