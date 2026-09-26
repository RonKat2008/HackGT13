import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { deskFetch } from "@/lib/desk";

export async function POST(request: Request) {
  const body = (await request.json()) as {
    mode?: string;
    email?: string;
    password?: string;
  };
  const path = body.mode === "signup" ? "/desk/signup" : "/desk/login";
  try {
    const account = await deskFetch<{ user_id: string }>(path, {
      method: "POST",
      body: JSON.stringify({
        email: body.email ?? "",
        password: body.password ?? "",
      }),
    });
    const jar = await cookies();
    jar.set("arx_desk", account.user_id, {
      httpOnly: true,
      sameSite: "lax",
      path: "/",
    });
    return NextResponse.json({ ok: true });
  } catch {
    return NextResponse.json({ ok: false }, { status: 400 });
  }
}
