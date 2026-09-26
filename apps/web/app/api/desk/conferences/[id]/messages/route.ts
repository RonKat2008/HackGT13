import { NextResponse } from "next/server";
import { deskFetch } from "@/lib/desk";
import { deskUser } from "@/lib/session";

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> },
) {
  if (!(await deskUser())) {
    return NextResponse.json({ error: "sign in" }, { status: 401 });
  }
  const { id } = await context.params;
  const history = await deskFetch(`/desk/conferences/${id}/messages`);
  return NextResponse.json(history);
}
