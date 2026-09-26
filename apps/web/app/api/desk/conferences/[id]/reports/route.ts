import { NextResponse } from "next/server";
import { deskRaw } from "@/lib/desk";
import { deskUser } from "@/lib/session";

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> },
) {
  if (!(await deskUser())) {
    return NextResponse.json({ error: "sign in" }, { status: 401 });
  }
  const { id } = await context.params;
  const upstream = await deskRaw(`/desk/conferences/${id}/reports.zip`);
  if (!upstream.ok) {
    return NextResponse.json({ error: "missing reports" }, { status: upstream.status });
  }
  return new NextResponse(await upstream.arrayBuffer(), {
    headers: {
      "Content-Type": "application/zip",
      "Content-Disposition": 'attachment; filename="reports.zip"',
    },
  });
}
