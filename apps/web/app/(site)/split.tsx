"use client";

import { signUp } from "@/lib/auth";
import Link from "next/link";
import { useEffect, useState } from "react";

type Desk = "author" | "conference";

export function AccountSplit({
  initial,
  error,
  sent,
}: {
  initial?: Desk;
  error?: string;
  sent?: boolean;
}) {
  const [picked, setPicked] = useState<Desk | null>(error || sent ? initial ?? null : null);

  useEffect(() => {
    if (!initial || error || sent) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setPicked(initial);
      return;
    }
    const frame = window.requestAnimationFrame(() => setPicked(initial));
    return () => window.cancelAnimationFrame(frame);
  }, [initial, error, sent]);

  function choose(desk: Desk) {
    if (picked) return;
    setPicked(desk);
  }

  const openClass = picked ? ` is-${picked}` : "";

  return (
    <section className={`desk-split${openClass}`} aria-label="Create an account">
      <Pane desk="author" picked={picked} error={error} sent={sent} onChoose={choose} onBack={() => setPicked(null)} />
      <Pane desk="conference" picked={picked} error={error} sent={sent} onChoose={choose} onBack={() => setPicked(null)} />
    </section>
  );
}

function Pane({
  desk,
  picked,
  error,
  sent,
  onChoose,
  onBack,
}: {
  desk: Desk;
  picked: Desk | null;
  error?: string;
  sent?: boolean;
  onChoose: (desk: Desk) => void;
  onBack: () => void;
}) {
  const open = picked === desk;
  const author = desk === "author";
  const copy = (
    <span className="desk-pane-copy">
      <span className="desk-pane-kicker">{author ? "Author" : "Conference"}</span>
      <span className="desk-pane-title">{author ? "One paper." : "The list."}</span>
      <span className="desk-pane-line">
        {author
          ? "Paste an arXiv id, then ask until the read is clear."
          : "A queue of papers you are responsible for."}
      </span>
    </span>
  );
  return (
    <div className={`desk-pane desk-pane-${desk}`}>
      {open ? (
        <div className="desk-pane-stage">
          {copy}
          {sent ? <SentNote author={author} /> : <SignupFields desk={desk} error={error} onBack={onBack} />}
        </div>
      ) : (
        <button type="button" className="desk-pane-hit" onClick={() => onChoose(desk)} disabled={picked !== null}>
          {copy}
        </button>
      )}
    </div>
  );
}

function SignupFields({
  desk,
  error,
  onBack,
}: {
  desk: Desk;
  error?: string;
  onBack: () => void;
}) {
  return (
    <form action={signUp} className="desk-pane-form">
      <input type="hidden" name="desk" value={desk} />
      <label className="flex flex-col gap-1 text-sm">
        Email
        <input
          name="email"
          type="email"
          required
          autoComplete="username"
          className="rounded-2xl bg-white px-4 py-3 text-[#1c1915] outline-none ring-[#e4dcd0] focus-visible:ring-2"
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Password
        <input
          name="password"
          type="password"
          required
          minLength={8}
          autoComplete="new-password"
          className="rounded-2xl bg-white px-4 py-3 text-[#1c1915] outline-none ring-[#e4dcd0] focus-visible:ring-2"
        />
      </label>
      {error ? (
        <p className="text-sm text-[#8c3a2f]" role="alert">
          {error}
        </p>
      ) : null}
      <button className="w-fit rounded-full bg-[#1c1915] px-5 py-3 text-sm text-[#f4f0e6]" type="submit">
        Create account
      </button>
      <button type="button" onClick={onBack} className="w-fit text-sm underline decoration-[#c4a15a] underline-offset-4">
        Other desk
      </button>
    </form>
  );
}

function SentNote({ author }: { author: boolean }) {
  return (
    <div className="desk-pane-form">
      <p className="font-[family-name:var(--desk-serif)] text-3xl">Check your email.</p>
      <p className="text-sm leading-6 opacity-80">
        Confirm the address, then come back and sign in. {author ? "Your papers" : "The list"} open after that.
      </p>
      <Link href="/login" className="text-sm underline decoration-[#c4a15a] underline-offset-4">
        Sign in
      </Link>
    </div>
  );
}
