import { redirect } from "next/navigation";
import { requireDeskUser } from "@/lib/session";

const DEMO_CONFERENCE_ID = "13b04c32-15d0-443b-a087-959b8016f3b8";

export default async function DeskHome() {
  await requireDeskUser();
  redirect(`/desk/${DEMO_CONFERENCE_ID}`);
}
