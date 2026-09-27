"use server";

import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

function authorNext(formData: FormData): boolean {
  const fromForm = String(formData.get("next") ?? "").trim();
  if (fromForm === "/author") return true;
  return false;
}

async function nextIsAuthor(formData: FormData): Promise<boolean> {
  if (authorNext(formData)) return true;
  const referer = (await headers()).get("referer");
  if (!referer) return false;
  try {
    return new URL(referer).searchParams.get("next") === "/author";
  } catch {
    return false;
  }
}

function chosenDesk(formData: FormData): "author" | "conference" {
  return String(formData.get("desk") ?? "") === "author" ? "author" : "conference";
}

function signupPath(desk: "author" | "conference", params: Record<string, string>) {
  return `/signup?${new URLSearchParams({ desk, ...params }).toString()}`;
}

export async function signIn(formData: FormData) {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const supabase = await createClient();
  const { data, error } = await supabase.auth.signInWithPassword({ email, password });
  const toAuthor =
    (await nextIsAuthor(formData)) || data.user?.user_metadata?.desk === "author";
  if (error) {
    const q = new URLSearchParams({ error: error.message });
    if (toAuthor) q.set("next", "/author");
    redirect(`/login?${q.toString()}`);
  }
  redirect(toAuthor ? "/author" : "/desk");
}

export async function signUp(formData: FormData) {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const desk = chosenDesk(formData);
  const home = desk === "author" ? "/author" : "/desk";
  if (password.length < 8) {
    redirect(signupPath(desk, { error: "Use a password of at least 8 characters." }));
  }
  const origin = (await headers()).get("origin") ?? "http://127.0.0.1:3000";
  const supabase = await createClient();
  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: {
      emailRedirectTo: `${origin}${home}`,
      data: { desk },
    },
  });
  if (error || !data.user) {
    const message = error?.message ?? "Could not create the account.";
    const shown = /rate limit/i.test(message)
      ? "Supabase paused confirmation email for this hour. Turn off Confirm email under Authentication, Providers, Email, then create the account again."
      : /signups are disabled/i.test(message)
        ? "The Email provider is off in Supabase. Turn Email back on, and leave Confirm email off, then create the account again."
        : message;
    redirect(signupPath(desk, { error: shown }));
  }
  if (!data.session) redirect(signupPath(desk, { sent: "1" }));
  redirect(home);
}

export async function signOut() {
  const supabase = await createClient();
  await supabase.auth.signOut();
  redirect("/");
}
