import { deskFetch, type ConferenceDesk, type Paper } from "@/lib/desk";
import { requireDeskUser } from "@/lib/session";
import Link from "next/link";
import { PaperRail } from "../../../rail";
import { DeskShell } from "../../../shell";
import { ReportView } from "./view";

export default async function ReportPage({
  params,
}: {
  params: Promise<{ id: string; jobId: string }>;
}) {
  const user = await requireDeskUser();
  const { id, jobId } = await params;
  const [desk, paper] = await Promise.all([
    deskFetch<ConferenceDesk>(`/desk/conferences/${id}`),
    deskFetch<Paper>(`/desk/papers/${jobId}`),
  ]);
  return (
    <DeskShell
      rail={
        <PaperRail
          conferenceId={id}
          name={desk.name}
          papers={desk.papers}
          running={desk.running}
          activeJobId={jobId}
          email={user.email}
        />
      }
    >
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex shrink-0 flex-wrap items-center gap-4 px-6 py-4 text-sm lg:px-10">
          <Link href={`/desk/${id}/${jobId}`} className="text-[#6b645c]">
            Back to the paper
          </Link>
          <a
            href={`/api/desk/papers/${jobId}/report`}
            className="rounded-full bg-[#1c1915] px-3 py-1.5 text-xs text-[#f4f0e6]"
          >
            Download
          </a>
          <a
            href={`/api/desk/conferences/${id}/reports`}
            className="text-xs underline decoration-[#c4a15a] underline-offset-4"
          >
            Download all as zip
          </a>
        </div>
        <ReportView paper={paper} />
      </div>
    </DeskShell>
  );
}
