import Link from "next/link";
import { type ConferenceProgress, type ConferenceSummary, type Paper } from "@/lib/desk";
import { AccountMenu } from "./account";
import { AddPapersForm } from "./add-form";
import { addPapers, deleteConference, deletePaper, runQueue, uploadPdf } from "./actions";
import { DeleteConferenceButton } from "./delete-conference";
import { ConferenceCount, PaperRows } from "./progress";

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
        PreSearch
      </Link>
      <p className="text-[11px] tracking-[0.16em] text-[#6b645c]">YOUR LISTS</p>
      <ul className="flex gap-3 overflow-x-auto lg:min-h-0 lg:flex-1 lg:flex-col lg:overflow-y-auto">
        {conferences.length === 0 ? (
          <li className="text-sm text-[#6b645c]">No lists yet.</li>
        ) : (
          conferences.map((conference) => (
            <li key={conference.conference_id} className="flex shrink-0 items-start gap-2 lg:shrink">
              <Link href={`/desk/${conference.conference_id}`} className="block min-w-0 flex-1 rounded-xl px-2 py-2 hover:bg-white/60">
                <span className="block font-[family-name:var(--desk-serif)] text-lg leading-tight">
                  {conference.name}
                </span>
                <span className="text-[11px] text-[#6b645c]">
                  {conference.queued} queued · {conference.running} running · {conference.finished} finished
                </span>
              </Link>
              <DeleteConferenceButton conferenceId={conference.conference_id} action={deleteConference} />
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
  progress,
  example = false,
}: {
  conferenceId: string;
  name: string;
  papers: Paper[];
  running: boolean;
  activeJobId?: string;
  email: string;
  progress?: ConferenceProgress;
  example?: boolean;
}) {
  const add = addPapers.bind(null, conferenceId);
  const upload = uploadPdf.bind(null, conferenceId);
  const remove = deletePaper.bind(null, conferenceId);
  const run = runQueue.bind(null, conferenceId);

  return (
    <aside className="flex max-h-52 shrink-0 flex-col gap-3 px-4 py-4 lg:max-h-none lg:min-h-0 lg:py-6">
      <div>
        <Link href="/desk" className="font-[family-name:var(--desk-serif)] text-2xl">
          PreSearch
        </Link>
        <p className="mt-4 font-[family-name:var(--desk-serif)] text-lg leading-tight">{name}</p>
        <ConferenceCount
          conferenceId={conferenceId}
          initialPapers={papers}
          initialProgress={progress}
          example={example}
        />
        <div className="mt-2">
          <DeleteConferenceButton conferenceId={conferenceId} action={deleteConference} />
        </div>
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
      <PaperRows
        conferenceId={conferenceId}
        initialPapers={papers}
        initialProgress={progress}
        activeJobId={activeJobId}
        example={example}
        remove={remove}
      />
      <AccountMenu email={email} />
    </aside>
  );
}
