import { NextResponse } from "next/server";
import { deskRaw } from "@/lib/desk";
import { deskUser } from "@/lib/session";

export async function GET(
  _request: Request,
  context: { params: Promise<{ jobId: string }> },
) {
  if (!(await deskUser())) {
    return NextResponse.json({ error: "sign in" }, { status: 401 });
  }
  const { jobId } = await context.params;
  const upstream = await deskRaw(`/desk/papers/${jobId}/pdf`);
  if (!upstream.ok) {
    return NextResponse.json({ error: "missing pdf" }, { status: upstream.status });
  }
  return new NextResponse(await upstream.arrayBuffer(), {
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": upstream.headers.get("content-disposition") ?? "inline",
    },
  });
}
