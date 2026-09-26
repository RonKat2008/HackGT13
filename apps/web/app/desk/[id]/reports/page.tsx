import { deskFetch, EXAMPLE_JOB_ID, type ConferenceDesk } from "@/lib/desk";
import { withExample } from "@/lib/example-paper";
import { categoryLines, paperLabel, summaryLine, summaryOf, verdictTone } from "@/lib/verdict";
import { requireDeskUser } from "@/lib/session";
import Link from "next/link";
import { PaperRail } from "../../rail";
import { DeskShell } from "../../shell";

export default async function ReportsPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ example?: string }>;
}) {
  const user = await requireDeskUser();
  const { id } = await params;
  const example = (await searchParams).example === "1";
  const desk = await deskFetch<ConferenceDesk>(`/desk/conferences/${id}`);
  const papers = example ? withExample(desk.papers) : desk.papers;
  return (
    <DeskShell
      rail={
        <PaperRail
          conferenceId={id}
          name={desk.name}
          papers={papers}
          running={desk.running}
          email={user.email}
        />
      }
    >
      <article className="min-h-0 flex-1 overflow-y-auto px-6 py-8 lg:px-10">
        <div className="mx-auto flex max-w-3xl flex-col gap-8">
          <header>
            <h1 className="font-[family-name:var(--desk-serif)] text-4xl leading-tight">Reports</h1>
            <p className="mt-3 max-w-xl text-sm leading-6 text-[#6b645c]">
              One document for each paper. A judged paper says what passed and what failed. Download the judged set as one zip.
            </p>
            <a
              href={`/api/desk/conferences/${id}/reports`}
              className="mt-5 inline-flex rounded-full bg-[#1c1915] px-3 py-1.5 text-xs text-[#f4f0e6]"
            >
              Download zip
            </a>
          </header>
          <ul className="flex flex-col gap-4">
            {papers.length === 0 ? (
              <li className="text-sm text-[#6b645c]">No papers on this list yet.</li>
            ) : (
              papers.map((paper) => (
                <li key={paper.job_id} className="rounded-2xl bg-white p-5 ring-1 ring-[#e4dcd0]">
                  <Link href={`/desk/${id}/${paper.job_id}${paper.job_id === EXAMPLE_JOB_ID ? "?example=1" : ""}`} className="block">
                    <span className="flex items-baseline justify-between gap-4">
                      <span className="font-[family-name:var(--desk-serif)] text-2xl leading-tight">
                        {paper.title || paper.arxiv_id}
                      </span>
                      <span className={`shrink-0 text-sm ${verdictTone(paper.status)}`}>{paperLabel(paper)}</span>
                    </span>
                    <span className="mt-1 block text-xs text-[#6b645c]">{paper.arxiv_id}</span>
                    {summaryLine(summaryOf(paper)) ? (
                      <span className="mt-3 block text-sm leading-6 text-[#1c1915]">{summaryLine(summaryOf(paper))}</span>
                    ) : paper.issues[0]?.reason ? (
                      <span className="mt-3 block text-sm leading-6 text-[#1c1915]">{paper.issues[0].reason}</span>
                    ) : null}
                    {categoryLines(summaryOf(paper))
                      .filter((line) => line.total > 0)
                      .map((line) => (
                        <span key={line.label} className="mt-1 block text-xs text-[#6b645c]">
                          {line.label} {line.value}
                        </span>
                      ))}
                  </Link>
                  {paper.job_id === EXAMPLE_JOB_ID ? null : (
                    <Link
                      href={`/desk/${id}/${paper.job_id}/report`}
                      className="mt-3 inline-block text-xs underline decoration-[#c4a15a] underline-offset-4"
                    >
                      Markdown
                    </Link>
                  )}
                </li>
              ))
            )}
          </ul>
        </div>
      </article>
    </DeskShell>
  );
}
