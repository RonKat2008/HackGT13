import { redirect } from "next/navigation";
import { deskFetch } from "@/lib/desk";
import { createClient } from "@/lib/supabase/server";

type DeskUser = { id: string; email: string };

export async function deskUser(): Promise<DeskUser | null> {
  const supabase = await createClient();
  const { data, error } = await supabase.auth.getClaims();
  const claims = data?.claims;
  if (error || !claims || typeof claims.sub !== "string") return null;
  const id = claims.sub;
  let email = typeof claims.email === "string" ? claims.email : "";
  if (!email) {
    const { data: userData } = await supabase.auth.getUser();
    email = userData.user?.email ?? "";
  }
  if (!email) return null;
  return { id, email };
}

export async function requireDeskUser(): Promise<DeskUser> {
  const user = await deskUser();
  if (!user) redirect("/login");
  try {
    await deskFetch("/desk/accounts/link", {
      method: "POST",
      body: JSON.stringify({ user_id: user.id, email: user.email }),
    });
  } catch {
    // A repeat visit is already linked. Creating a list reports a real failure.
  }
  return user;
}
