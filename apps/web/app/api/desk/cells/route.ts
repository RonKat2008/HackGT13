import { NextResponse } from "next/server";
import { deskFetch } from "@/lib/desk";
import { deskUser } from "@/lib/session";

export async function POST(request: Request) {
  if (!(await deskUser())) {
    return NextResponse.json({ error: "sign in" }, { status: 401 });
  }
  const body = (await request.json()) as { code?: string };
  const result = await deskFetch("/desk/cells", {
    method: "POST",
    body: JSON.stringify({ code: body.code ?? "" }),
  });
  return NextResponse.json(result);
}
