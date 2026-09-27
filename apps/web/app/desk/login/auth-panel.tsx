"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function AuthPanel({ failed }: { failed: boolean }) {
  const [error, setError] = useState(failed);
  const [pending, setPending] = useState(false);
  const router = useRouter();

  async function submit(formData: FormData) {
    setPending(true);
    setError(false);
    const response = await fetch("/api/desk/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mode: "login",
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
      <form action={submit} className="flex flex-col gap-4">
        <h1 className="desk-rise font-[family-name:var(--desk-serif)] text-5xl leading-tight">
          A desk for the papers you are responsible for.
        </h1>
        <p className="text-sm leading-6 text-[#6b645c]">
          Sign in, then the desk opens the one list.
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
            minLength={1}
            autoComplete="current-password"
            className="rounded-2xl bg-white px-4 py-3 outline-none"
          />
        </label>
        {error ? (
          <p className="text-sm text-[#8c3a2f]" role="alert">
            That email or password does not match.
          </p>
        ) : null}
        <button
          className="rounded-full bg-[#1c1915] px-5 py-3 text-sm text-[#f4f0e6]"
          type="submit"
        >
          {pending ? "…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
