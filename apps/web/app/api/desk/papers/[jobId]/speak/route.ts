import { NextResponse } from "next/server";
import { deskFetch } from "@/lib/desk";
import { deskUser } from "@/lib/session";

export async function POST(
  request: Request,
  context: { params: Promise<{ jobId: string }> },
) {
  if (!(await deskUser())) {
    return NextResponse.json({ error: "sign in" }, { status: 401 });
  }
  const { jobId } = await context.params;
  const body = (await request.json().catch(() => ({}))) as {
    question?: string;
    claim?: string;
  };
  try {
    const result = await deskFetch(`/desk/papers/${jobId}/speak`, {
      method: "POST",
      body: JSON.stringify({
        question: body.question ?? "",
        claim: body.claim ?? "",
      }),
    });
    return NextResponse.json(result);
  } catch {
    return NextResponse.json({ error: "The desk could not speak that." }, { status: 502 });
  }
}
