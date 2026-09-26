"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function AuthPanel({ failed }: { failed: boolean }) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [error, setError] = useState(failed);
  const [pending, setPending] = useState(false);
  const router = useRouter();
  const signup = mode === "signup";

  async function submit(formData: FormData) {
    setPending(true);
    setError(false);
    const response = await fetch("/api/desk/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mode,
        email: formData.get("email"),
        password: formData.get("password"),
      }),
    });
    setPending(false);
    if (!response.ok) {
      setError(true);
      return;
    }
    router.push("/desk");
    router.refresh();
  }

  return (
    <div className="mt-10">
      <div className="mb-6 flex gap-6 text-sm">
        <button
          type="button"
          onClick={() => {
            setMode("login");
            setError(false);
          }}
          className={signup ? "text-[#6b645c]" : "text-[#1c1915]"}
        >
          Sign in
        </button>
        <button
          type="button"
          onClick={() => {
            setMode("signup");
            setError(false);
          }}
          className={signup ? "text-[#1c1915]" : "text-[#6b645c]"}
        >
          Create account
        </button>
      </div>
      <form action={submit} className="flex flex-col gap-4">
        <h1
          key={mode}
          className="desk-rise font-[family-name:var(--desk-serif)] text-5xl leading-tight"
        >
          {signup
            ? "Start a desk of your own."
            : "A desk for the papers you are responsible for."}
        </h1>
        <p className="text-sm leading-6 text-[#6b645c]">
          {signup
            ? "Your conferences and paper lists stay on this account."
            : "Sign in, open a conference, and let the agent work your list."}
        </p>
        <label className="flex flex-col gap-1 text-sm">
          Email
          <input
            name="email"
            type="email"
            required
            autoComplete="username"
            className="rounded-2xl bg-white px-4 py-3 outline-none"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Password
          <input
            name="password"
            type="password"
            required
            minLength={signup ? 8 : 1}
            autoComplete={signup ? "new-password" : "current-password"}
            className="rounded-2xl bg-white px-4 py-3 outline-none"
          />
        </label>
        {error ? (
          <p className="text-sm text-[#8c3a2f]" role="alert">
            {signup
              ? "That email is already in use, or the password is too short."
              : "That email or password does not match."}
          </p>
        ) : null}
        <button
          className="rounded-full bg-[#1c1915] px-5 py-3 text-sm text-[#f4f0e6]"
          type="submit"
        >
          {pending ? "…" : signup ? "Create account" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
