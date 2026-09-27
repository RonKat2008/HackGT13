import { NextResponse } from "next/server";
import { deskUser } from "@/lib/session";

const base = process.env.ORCHESTRATOR_URL ?? "http://127.0.0.1:8000";

export async function POST(
  request: Request,
  context: { params: Promise<{ jobId: string }> },
) {
  if (!(await deskUser())) {
    return NextResponse.json({ error: "sign in" }, { status: 401 });
  }
  const { jobId } = await context.params;
  const client = (await request.json().catch(() => ({}))) as { question?: string };
  const response = await fetch(`${base}/author/papers/${jobId}/ask`, {
    method: "POST",
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question: client.question ?? "" }),
  });
  const body = await response.json().catch(() => ({}));
  return NextResponse.json(body, { status: response.status });
}
