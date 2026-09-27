import { NextResponse } from "next/server";
import { deskFetch } from "@/lib/desk";
import { deskUser } from "@/lib/session";

export async function POST(request: Request) {
  if (!(await deskUser())) {
    return NextResponse.json({ error: "sign in" }, { status: 401 });
  }
  const body = (await request.json().catch(() => ({}))) as {
    text?: string;
    papers?: { job_id?: string; title?: string; arxiv_id?: string }[];
  };
  const papers = Array.isArray(body.papers) ? body.papers : [];
  try {
    const result = await deskFetch("/voice/command", {
      method: "POST",
      body: JSON.stringify({
        text: typeof body.text === "string" ? body.text : "",
        papers: papers.map((paper) => ({
          job_id: paper.job_id ?? "",
          title: paper.title ?? "",
          arxiv_id: paper.arxiv_id ?? "",
        })),
      }),
    });
    return NextResponse.json(result);
  } catch {
    return NextResponse.json({ error: "Voice is unavailable." }, { status: 502 });
  }
}
