import Link from "next/link";
import { EXAMPLE_JOB_ID, type ConferenceSummary, type Paper } from "@/lib/desk";
import { paperLabel, verdictTone } from "@/lib/verdict";
import { AccountMenu } from "./account";
import { AddPapersForm } from "./add-form";
import { addPapers, deletePaper, runQueue, uploadPdf } from "./actions";
import { MorphLink } from "./morph-link";

function dot(status: string): string {
  if (status === "contradicted" || status === "error") return "bg-[#8c3a2f]";
  if (status === "passed") return "bg-[#2f6b4f]";
  if (status === "running") return "bg-[#c4a15a]";
  return "bg-[#cfc6b8]";
}

export function ConferenceRail({
  conferences,
  email,
}: {
  conferences: ConferenceSummary[];
  email: string;
}) {
  return (
    <aside className="flex max-h-44 shrink-0 flex-col gap-3 px-4 py-4 lg:max-h-none lg:min-h-0 lg:py-6">
      <Link href="/desk" className="font-[family-name:var(--desk-serif)] text-2xl">
        ArxAudit
      </Link>
      <p className="text-[11px] tracking-[0.16em] text-[#6b645c]">YOUR LISTS</p>
      <ul className="flex gap-3 overflow-x-auto lg:min-h-0 lg:flex-1 lg:flex-col lg:overflow-y-auto">
        {conferences.length === 0 ? (
          <li className="text-sm text-[#6b645c]">No lists yet.</li>
        ) : (
          conferences.map((conference) => (
            <li key={conference.conference_id} className="shrink-0 lg:shrink">
              <Link href={`/desk/${conference.conference_id}`} className="block rounded-xl px-2 py-2 hover:bg-white/60">
                <span className="block font-[family-name:var(--desk-serif)] text-lg leading-tight">
                  {conference.name}
                </span>
                <span className="text-[11px] text-[#6b645c]">
                  {conference.queued} queued · {conference.running} running · {conference.finished} finished
                </span>
              </Link>
            </li>
          ))
        )}
      </ul>
      <AccountMenu email={email} />
    </aside>
  );
}

export function PaperRail({
  conferenceId,
  name,
  papers,
  running,
  activeJobId,
  email,
}: {
  conferenceId: string;
  name: string;
  papers: Paper[];
  running: boolean;
  activeJobId?: string;
  email: string;
}) {
  const add = addPapers.bind(null, conferenceId);
  const upload = uploadPdf.bind(null, conferenceId);
  const remove = deletePaper.bind(null, conferenceId);
  const run = runQueue.bind(null, conferenceId);

  return (
    <aside className="flex max-h-52 shrink-0 flex-col gap-3 px-4 py-4 lg:max-h-none lg:min-h-0 lg:py-6">
      <div>
        <Link href="/desk" className="font-[family-name:var(--desk-serif)] text-2xl">
          ArxAudit
        </Link>
        <p className="mt-4 font-[family-name:var(--desk-serif)] text-lg leading-tight">{name}</p>
        <p className="mt-1 text-[11px] text-[#6b645c]">{papers.length} papers</p>
      </div>
      <form action={run} className="relative z-10 flex shrink-0 items-center gap-2">
        <input
          name="cap"
          inputMode="numeric"
          placeholder="all"
          aria-label="Papers this run"
          className="w-14 bg-transparent px-1 py-1 text-xs outline-none"
        />
        <button className="rounded-full bg-[#1c1915] px-3 py-1.5 text-xs text-[#f4f0e6]" type="submit">
          {running ? "Running" : "Run"}
        </button>
      </form>
      <AddPapersForm action={add} uploadAction={upload} />
      <div className="relative z-10 flex gap-3 text-xs">
        <Link href={`/desk/${conferenceId}/reports`} className="underline decoration-[#c4a15a] underline-offset-4">
          Reports
        </Link>
        <a
          href={`/api/desk/conferences/${conferenceId}/reports`}
          className="underline decoration-[#c4a15a] underline-offset-4"
        >
          Download zip
        </a>
      </div>
      <ul className="relative z-0 flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto">
        {papers.map((paper) => {
          const active = paper.job_id === activeJobId;
          const title = paper.title || "Unread paper";
          return (
            <li key={paper.job_id} className="flex shrink-0 items-start gap-1 lg:shrink">
              <MorphLink
                href={`/desk/${conferenceId}/${paper.job_id}${paper.job_id === EXAMPLE_JOB_ID ? "?example=1" : ""}`}
                className={`flex min-w-0 flex-1 items-start gap-2 rounded-xl px-2 py-2 ${active ? "bg-white/80" : "hover:bg-white/60"}`}
              >
                <span
                  className={`mt-1.5 size-1.5 shrink-0 rounded-full ${dot(paper.status)} ${paper.status === "running" ? "desk-pulse" : ""}`}
                />
                <span className="min-w-0">
                  <span className="block text-sm leading-5">{title}</span>
                  <span className="text-[11px] text-[#6b645c]">
                    {paper.arxiv_id}
                    {paper.status === "passed" || paper.status === "contradicted" || paper.status === "error" ? (
                      <>
                        {" · "}
                        <span className={verdictTone(paper.status)}>{paperLabel(paper)}</span>
                      </>
                    ) : null}
                  </span>
                </span>
              </MorphLink>
              <form action={remove} className="shrink-0 pt-1">
                <input type="hidden" name="job_id" value={paper.job_id} />
                <input type="hidden" name="open" value={active ? "1" : ""} />
                <button
                  type="submit"
                  className="px-1 py-1 text-[11px] text-[#6b645c] underline decoration-[#c4a15a] underline-offset-4"
                >
                  Delete
                </button>
              </form>
            </li>
          );
        })}
      </ul>
      <AccountMenu email={email} />
    </aside>
  );
}
