import { deskFetch, type ConferenceDesk } from "@/lib/desk";
import { withExample } from "@/lib/example-paper";
import { requireDeskUser } from "@/lib/session";
import { DeskViews } from "../progress";
import { PaperRail } from "../rail";
import { DeskShell } from "../shell";

export default async function ConferencePage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ example?: string; view?: string }>;
}) {
  const user = await requireDeskUser();
  const { id } = await params;
  const { example: exampleFlag, view } = await searchParams;
  const example = exampleFlag === "1";
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
      <DeskViews
        conferenceId={id}
        conferenceName={desk.name}
        initial={papers}
        example={example}
        initialView={view === "summary" ? "summary" : "chat"}
      />
    </DeskShell>
  );
}
