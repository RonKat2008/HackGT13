import { NextResponse } from "next/server";
import { deskFetch } from "@/lib/desk";
import { deskUser } from "@/lib/session";

export async function GET(request: Request) {
  if (!(await deskUser())) {
    return NextResponse.json({ error: "sign in" }, { status: 401 });
  }
  const conferenceId = new URL(request.url).searchParams.get("conference_id");
  if (!conferenceId) {
    return NextResponse.json({ error: "conference_id" }, { status: 400 });
  }
  const metrics = await deskFetch(`/desk/metrics?conference_id=${conferenceId}`);
  return NextResponse.json(metrics);
}
