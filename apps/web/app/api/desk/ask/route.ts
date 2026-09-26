import { NextResponse } from "next/server";
import { deskFetch } from "@/lib/desk";
import { deskUser } from "@/lib/session";

export async function POST(request: Request) {
  if (!(await deskUser())) {
    return NextResponse.json({ error: "sign in" }, { status: 401 });
  }
  const body = (await request.json()) as {
    conferenceId?: string;
    question?: string;
    mentions?: string[];
  };
  const result = await deskFetch(`/desk/conferences/${body.conferenceId}/ask`, {
    method: "POST",
    body: JSON.stringify({
      question: body.question ?? "",
      mentions: body.mentions ?? [],
    }),
  });
  return NextResponse.json(result);
}
