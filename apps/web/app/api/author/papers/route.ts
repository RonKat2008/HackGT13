import { NextResponse } from "next/server";
import { deskFetch } from "@/lib/desk";
import { deskUser } from "@/lib/session";

const base = process.env.ORCHESTRATOR_URL ?? "http://127.0.0.1:8000";

export async function GET() {
  const user = await deskUser();
  if (!user) {
    return NextResponse.json({ error: "sign in" }, { status: 401 });
  }
  const listed = await deskFetch(`/author/papers?owner=${encodeURIComponent(user.id)}`);
  return NextResponse.json(listed);
}

export async function POST(request: Request) {
  const user = await deskUser();
  if (!user) {
    return NextResponse.json({ error: "sign in" }, { status: 401 });
  }
  const contentType = request.headers.get("content-type") ?? "";
  if (contentType.includes("multipart/form-data")) {
    const incoming = await request.formData();
    const upstream = new FormData();
    const pdf = incoming.get("pdf");
    if (pdf instanceof File) {
      upstream.append("pdf", pdf);
    }
    const response = await fetch(
      `${base}/author/papers?owner=${encodeURIComponent(user.id)}`,
      { method: "POST", cache: "no-store", body: upstream },
    );
    const body = await response.json().catch(() => ({}));
    return NextResponse.json(body, { status: response.status });
  }
  const client = (await request.json().catch(() => ({}))) as { arxiv_id?: string };
  const response = await fetch(`${base}/author/papers`, {
    method: "POST",
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ owner: user.id, arxiv_id: client.arxiv_id ?? "" }),
  });
  const body = await response.json().catch(() => ({}));
  return NextResponse.json(body, { status: response.status });
}
