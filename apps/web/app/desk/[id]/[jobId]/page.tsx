import { deskFetch, EXAMPLE_JOB_ID, type ConferenceDesk, type Paper } from "@/lib/desk";
import { examplePaper, withExample } from "@/lib/example-paper";
import { requireDeskUser } from "@/lib/session";
import { PaperRail } from "../../rail";
import { DeskShell } from "../../shell";
import { Workflow } from "./workflow";

export default async function PaperPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string; jobId: string }>;
  searchParams: Promise<{ part?: string; example?: string; ask?: string }>;
}) {
  const user = await requireDeskUser();
  const { id, jobId } = await params;
  const { part, example, ask } = await searchParams;
  const showExample = example === "1" || jobId === EXAMPLE_JOB_ID;
  const desk = await deskFetch<ConferenceDesk>(`/desk/conferences/${id}`);
  const papers = showExample ? withExample(desk.papers) : desk.papers;
  const paper: Paper =
    jobId === EXAMPLE_JOB_ID ? examplePaper() : await deskFetch<Paper>(`/desk/papers/${jobId}`);
  return (
    <DeskShell
      rail={
        <PaperRail
          conferenceId={id}
          name={desk.name}
          papers={papers}
          running={desk.running}
          activeJobId={jobId}
          email={user.email}
        />
      }
    >
      <Workflow
        conferenceId={id}
        conferenceName={desk.name}
        papers={papers}
        initial={paper}
        part={part ?? ""}
        ask={ask === "1"}
      />
    </DeskShell>
  );
}
