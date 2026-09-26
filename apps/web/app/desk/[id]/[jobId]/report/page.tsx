import { deskFetch, deskRaw, type ConferenceDesk } from "@/lib/desk";
import { requireDeskUser } from "@/lib/session";
import Link from "next/link";
import { PaperRail } from "../../../rail";
import { DeskShell } from "../../../shell";
import { ReportBody } from "./body";

export default async function ReportPage({
  params,
}: {
  params: Promise<{ id: string; jobId: string }>;
}) {
  const user = await requireDeskUser();
  const { id, jobId } = await params;
  const [desk, report] = await Promise.all([
    deskFetch<ConferenceDesk>(`/desk/conferences/${id}`),
    deskRaw(`/desk/papers/${jobId}/report`),
  ]);
  const markdown = report.ok ? await report.text() : "This report could not be opened.";
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
      <article className="min-h-0 flex-1 overflow-y-auto px-6 py-8 lg:px-10">
        <div className="mb-8 flex flex-wrap items-center gap-4 text-sm">
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
        <ReportBody markdown={markdown} />
      </article>
    </DeskShell>
  );
}
