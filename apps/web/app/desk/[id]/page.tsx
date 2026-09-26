import { deskFetch, type ConferenceDesk } from "@/lib/desk";
import { requireDeskUser } from "@/lib/session";
import { DeskViews } from "../progress";
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
      <DeskViews conferenceId={id} conferenceName={desk.name} initial={desk.papers} />
    </DeskShell>
  );
}
