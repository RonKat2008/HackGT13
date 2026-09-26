import { deskFetch, type ConferenceDesk, type Paper } from "@/lib/desk";
import { requireDeskUser } from "@/lib/session";
import { PaperRail } from "../../rail";
import { DeskShell } from "../../shell";
import { Workflow } from "./workflow";

export default async function PaperPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string; jobId: string }>;
  searchParams: Promise<{ part?: string }>;
}) {
  const user = await requireDeskUser();
  const { id, jobId } = await params;
  const { part } = await searchParams;
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
      <Workflow
        conferenceId={id}
        conferenceName={desk.name}
        papers={desk.papers}
        initial={paper}
        part={part ?? ""}
      />
    </DeskShell>
  );
}
