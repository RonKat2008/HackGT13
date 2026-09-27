import Link from "next/link";
import { deskUser } from "@/lib/session";

export async function SiteNav() {
  const user = await deskUser();
  return (
    <header className="sticky top-0 z-20 border-b border-[#e4dcd0] bg-[#f4f0e6]/90 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-6 px-6 py-4">
        <Link href="/" className="font-[family-name:var(--desk-serif)] text-2xl tracking-tight">
          ArxAudit
        </Link>
        <nav className="flex items-center gap-5 text-sm" aria-label="Site">
          <Link href="/#how" className="hidden text-[#6b645c] sm:inline">
            How it works
          </Link>
          {user ? (
            <Link
              href="/desk"
              className="rounded-full bg-[#1c1915] px-4 py-2 text-[#f4f0e6]"
            >
              Open the desk
            </Link>
          ) : (
            <Link
              href="/login"
              className="rounded-full bg-[#1c1915] px-4 py-2 text-[#f4f0e6]"
            >
              Sign in
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}
