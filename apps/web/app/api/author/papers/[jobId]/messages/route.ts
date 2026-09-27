import { NextResponse } from "next/server";
import { deskFetch } from "@/lib/desk";
import { deskUser } from "@/lib/session";

export async function GET(
  _request: Request,
  context: { params: Promise<{ jobId: string }> },
) {
  if (!(await deskUser())) {
    return NextResponse.json({ error: "sign in" }, { status: 401 });
  }
  const { jobId } = await context.params;
  const history = await deskFetch(`/author/papers/${jobId}/messages`);
  return NextResponse.json(history);
}

export async function DELETE(
  _request: Request,
  context: { params: Promise<{ jobId: string }> },
) {
  if (!(await deskUser())) {
    return NextResponse.json({ error: "sign in" }, { status: 401 });
  }
  const { jobId } = await context.params;
  const result = await deskFetch(`/author/papers/${jobId}/messages`, { method: "DELETE" });
  return NextResponse.json(result);
}
