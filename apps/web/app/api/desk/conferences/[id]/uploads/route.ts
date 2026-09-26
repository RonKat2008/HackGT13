import { NextResponse } from "next/server";
import { deskUser } from "@/lib/session";

const base = process.env.ORCHESTRATOR_URL ?? "http://127.0.0.1:8000";

export async function POST(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  if (!(await deskUser())) {
    return NextResponse.json({ error: "sign in" }, { status: 401 });
  }
  const { id } = await context.params;
  const incoming = await request.formData();
  const file = incoming.get("file");
  const upstream = new FormData();
  if (file instanceof File) {
    upstream.append("file", file);
  }
  const response = await fetch(`${base}/desk/conferences/${id}/uploads`, {
    method: "POST",
    cache: "no-store",
    body: upstream,
  });
  const body = await response.json().catch(() => ({}));
  return NextResponse.json(body, { status: response.status });
}
