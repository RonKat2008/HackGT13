import { readFileSync } from "node:fs";
import path from "node:path";
import { NextResponse } from "next/server";
import { deskRaw, EXAMPLE_JOB_ID } from "@/lib/desk";
import { deskUser } from "@/lib/session";

export async function GET(
  _request: Request,
  context: { params: Promise<{ jobId: string }> },
) {
  if (!(await deskUser())) {
    return NextResponse.json({ error: "sign in" }, { status: 401 });
  }
  const { jobId } = await context.params;
  if (jobId === EXAMPLE_JOB_ID) {
    const file = path.join(process.cwd(), "..", "..", "services", "orchestrator", "fixtures", "demo_paper.pdf");
    return new NextResponse(readFileSync(file), {
      headers: { "Content-Type": "application/pdf", "Content-Disposition": "inline" },
    });
  }
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
