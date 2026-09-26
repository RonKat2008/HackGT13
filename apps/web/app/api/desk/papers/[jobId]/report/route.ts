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
  const upstream = await deskRaw(`/desk/papers/${jobId}/report?download=1`);
  if (!upstream.ok) {
    return NextResponse.json({ error: "missing report" }, { status: upstream.status });
  }
  return new NextResponse(await upstream.arrayBuffer(), {
    headers: {
      "Content-Type": upstream.headers.get("content-type") ?? "text/markdown; charset=utf-8",
      "Content-Disposition":
        upstream.headers.get("content-disposition") ?? `attachment; filename="${jobId}.md"`,
    },
  });
}
