import { deskFetch, type ConferenceDesk } from "@/lib/desk";
import { requireDeskUser } from "@/lib/session";
import { AskDesk } from "./ask";
import { PaperRail } from "../rail";
import { DeskShell } from "../shell";

export default async function ConferencePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const user = await requireDeskUser();
  const { id } = await params;
  const desk = await deskFetch<ConferenceDesk>(`/desk/conferences/${id}`);

  return (
    <DeskShell
      rail={
        <PaperRail
          conferenceId={id}
          name={desk.name}
          papers={desk.papers}
          running={desk.running}
          email={user.email}
        />
      }
    >
      <AskDesk conferenceId={id} conferenceName={desk.name} papers={desk.papers} />
    </DeskShell>
  );
}
