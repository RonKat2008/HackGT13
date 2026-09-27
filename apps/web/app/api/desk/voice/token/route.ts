import { NextResponse } from "next/server";
import { deskFetch } from "@/lib/desk";
import { deskUser } from "@/lib/session";

export async function POST() {
  if (!(await deskUser())) {
    return NextResponse.json({ error: "sign in" }, { status: 401 });
  }
  try {
    const result = await deskFetch<{ value: string; expires_at: number | null }>("/voice/token", {
      method: "POST",
    });
    return NextResponse.json({ value: result.value, expires_at: result.expires_at });
  } catch (error) {
    const message = error instanceof Error ? error.message : "";
    if (message.includes("(503)")) {
      return NextResponse.json({ error: "voice key missing" }, { status: 503 });
    }
    return NextResponse.json({ error: "Voice is unavailable." }, { status: 502 });
  }
}
