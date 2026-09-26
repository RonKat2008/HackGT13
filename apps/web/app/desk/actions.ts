"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { deskFetch } from "@/lib/desk";

const base = process.env.ORCHESTRATOR_URL ?? "http://127.0.0.1:8000";

type AddState = { error: string; added: number };

export async function addPapers(
  conferenceId: string,
  _state: AddState,
  formData: FormData,
): Promise<AddState> {
  const lines = String(formData.get("lines") ?? "").split("\n");
  if (!lines.some((line) => line.trim())) {
    return { error: "Paste at least one arXiv id.", added: 0 };
  }
  const response = await fetch(`${base}/desk/conferences/${conferenceId}/submissions`, {
    method: "POST",
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lines }),
  });
  const body = (await response.json().catch(() => ({}))) as {
    detail?: string;
    added?: number;
    refreshed?: number;
  };
  if (!response.ok) {
    return {
      error: typeof body.detail === "string" ? body.detail : "Those ids could not be added.",
      added: 0,
    };
  }
  const added = body.added ?? 0;
  const refreshed = body.refreshed ?? 0;
  if (added === 0 && refreshed === 0) {
    return { error: "Those papers are already on this list.", added: 0 };
  }
  revalidatePath(`/desk/${conferenceId}`);
  revalidatePath("/desk", "layout");
  return { error: "", added: added + refreshed };
}

export async function uploadPdf(
  conferenceId: string,
  _state: AddState,
  formData: FormData,
): Promise<AddState> {
  const file = formData.get("file");
  if (!(file instanceof File) || file.size === 0) {
    return { error: "Choose a PDF to upload.", added: 0 };
  }
  const body = new FormData();
  body.append("file", file);
  const response = await fetch(`${base}/desk/conferences/${conferenceId}/uploads`, {
    method: "POST",
    cache: "no-store",
    body,
  });
  const payload = (await response.json().catch(() => ({}))) as {
    detail?: string;
    added?: number;
  };
  if (!response.ok) {
    return {
      error: typeof payload.detail === "string" ? payload.detail : "That PDF could not be uploaded.",
      added: 0,
    };
  }
  const added = payload.added ?? 0;
  if (added === 0) {
    return { error: "That paper is already on this list.", added: 0 };
  }
  revalidatePath(`/desk/${conferenceId}`);
  revalidatePath("/desk", "layout");
  return { error: "", added };
}

export async function deletePaper(conferenceId: string, formData: FormData) {
  const jobId = String(formData.get("job_id") ?? "").trim();
  const open = String(formData.get("open") ?? "") === "1";
  if (!jobId) return;
  const response = await fetch(`${base}/desk/conferences/${conferenceId}/papers/${jobId}`, {
    method: "DELETE",
    cache: "no-store",
  });
  if (!response.ok && response.status !== 404) return;
  revalidatePath(`/desk/${conferenceId}`);
  revalidatePath("/desk", "layout");
  if (open) redirect(`/desk/${conferenceId}`);
}

export async function runQueue(conferenceId: string, formData: FormData) {
  const raw = String(formData.get("cap") ?? "").trim();
  const cap = raw === "" ? null : Number(raw);
  await deskFetch(`/desk/conferences/${conferenceId}/run`, {
    method: "POST",
    body: JSON.stringify({ cap }),
  });
  revalidatePath(`/desk/${conferenceId}`);
  revalidatePath("/desk", "layout");
}
