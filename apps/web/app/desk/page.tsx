import { redirect } from "next/navigation";
import { deskFetch, type ConferenceSummary } from "@/lib/desk";
import { requireDeskUser } from "@/lib/session";
import { ConferenceRail } from "./rail";
import { DeskShell } from "./shell";

async function createConference(formData: FormData) {
  "use server";
  const owner = (await requireDeskUser()).id;
  const name = String(formData.get("name") ?? "").trim();
  const contact = String(formData.get("contact_email") ?? "").trim();
  if (!name || !contact) redirect("/desk?error=1");
  const created = await deskFetch<{ conference_id: string }>("/desk/accounts/conferences", {
    method: "POST",
    body: JSON.stringify({ owner, name, contact_email: contact }),
  });
  redirect(`/desk/${created.conference_id}`);
}

export default async function DeskHome({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const user = await requireDeskUser();
  const owner = user.id;
  const failed = Boolean((await searchParams).error);
  let conferences: ConferenceSummary[] = [];
  try {
    conferences = await deskFetch<ConferenceSummary[]>(
      `/desk/conferences?owner=${encodeURIComponent(owner)}`,
    );
  } catch {
    conferences = [];
  }

  return (
    <DeskShell rail={<ConferenceRail conferences={conferences} email={user.email} />}>
      <main className="flex h-full min-h-0 flex-col justify-center px-8 py-10 lg:px-16">
        <p className="text-[11px] tracking-[0.16em] text-[#8c3a2f]">CONFERENCES</p>
        <h1 className="mt-3 max-w-xl font-[family-name:var(--desk-serif)] text-5xl leading-tight">
          A list of your own.
        </h1>
        <p className="mt-4 max-w-md text-sm leading-6 text-[#6b645c]">
          Each list is yours. The agent walks the papers you add.
        </p>
        <form action={createConference} className="mt-10 flex max-w-lg flex-col gap-4">
          <label className="flex flex-col gap-1 text-sm">
            Name
            <input name="name" required className="rounded-2xl bg-white px-4 py-3 outline-none ring-[#e4dcd0] focus-visible:ring-2" />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Chair email
            <input name="contact_email" type="email" required className="rounded-2xl bg-white px-4 py-3 outline-none ring-[#e4dcd0] focus-visible:ring-2" />
          </label>
          {failed ? (
            <p className="text-sm text-[#8c3a2f]" role="alert">
              Name and chair email are both required.
            </p>
          ) : null}
          <button className="w-fit rounded-full bg-[#1c1915] px-5 py-3 text-sm text-[#f4f0e6]" type="submit">
            New conference
          </button>
        </form>
      </main>
    </DeskShell>
  );
}
