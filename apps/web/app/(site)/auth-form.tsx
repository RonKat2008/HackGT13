import { signIn } from "@/lib/auth";
import Link from "next/link";

export function AuthForm({
  error,
  sent,
  next,
}: {
  mode?: "login" | "signup";
  error?: string;
  sent?: boolean;
  next?: string;
}) {
  const author = next === "/author";
  return (
    <main className="mx-auto grid min-h-[calc(100dvh-4.5rem)] max-w-6xl items-center gap-12 px-6 py-16 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1fr)]">
      <div>
        <p className="text-[11px] tracking-[0.18em] text-[#8c3a2f]">
          {author ? "FOR AUTHORS" : "FOR CONFERENCE CHAIRS"}
        </p>
        <h1 className="mt-4 max-w-md font-[family-name:var(--desk-serif)] text-5xl leading-tight">
          {author ? "One paper, one read." : "The papers you are responsible for."}
        </h1>
        <p className="mt-6 max-w-sm text-sm leading-6 text-[#6b645c]">
          {author
            ? "Sign in, then the author desk opens that paper."
            : "Sign in, then the desk opens the one list."}
        </p>
      </div>
      <div className="w-full max-w-md">
        {sent ? (
          <div>
            <h2 className="font-[family-name:var(--desk-serif)] text-4xl">Check your email.</h2>
            <p className="mt-4 text-sm leading-6 text-[#6b645c]">
              Confirm the address, then come back and sign in. The desk opens after that.
            </p>
          </div>
        ) : (
          <form action={signIn} className="flex flex-col gap-4">
            {author ? <input type="hidden" name="next" value="/author" /> : null}
            <label className="flex flex-col gap-1 text-sm">
              Email
              <input
                name="email"
                type="email"
                required
                autoComplete="username"
                className="rounded-2xl bg-white px-4 py-3 outline-none ring-[#e4dcd0] focus-visible:ring-2"
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
                className="rounded-2xl bg-white px-4 py-3 outline-none ring-[#e4dcd0] focus-visible:ring-2"
              />
            </label>
            {error ? (
              <p className="text-sm text-[#8c3a2f]" role="alert">
                {error}
              </p>
            ) : null}
            <button className="mt-2 w-fit rounded-full bg-[#1c1915] px-5 py-3 text-sm text-[#f4f0e6]" type="submit">
              Sign in
            </button>
            <Link
              href={author ? "/signup?desk=author" : "/signup"}
              className="text-sm underline decoration-[#c4a15a] underline-offset-4"
            >
              Create an account
            </Link>
          </form>
        )}
      </div>
    </main>
  );
}
