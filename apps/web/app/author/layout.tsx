import Link from "next/link";
import { signOut } from "@/lib/auth";
import { deskUser } from "@/lib/session";
import { VoiceDesk } from "../desk/voice-desk";
import "../desk/motion.css";

export const metadata = {
  title: "PreSearch — Author",
  description: "Read one paper and ask about what the audit found.",
};

export default async function AuthorLayout({ children }: { children: React.ReactNode }) {
  const user = await deskUser();
  return (
    <div className="flex h-dvh min-h-0 flex-col bg-[#f4f0e6] text-[#1c1915] [font-family:'IBM_Plex_Sans',ui-sans-serif,system-ui,sans-serif]">
      <link
        rel="stylesheet"
        href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=Newsreader:opsz,wght@6..72,400;500;600&display=swap"
      />
      <style>{`
        html, body { background: #f4f0e6; color: #1c1915; height: 100%; }
        :root { --desk-serif: "Newsreader", ui-serif, Georgia, serif; }
        @media (prefers-reduced-motion: reduce) {
          .author-thread * { transition: none !important; animation: none !important; scroll-behavior: auto !important; }
        }
      `}</style>
      <header className="flex shrink-0 items-center justify-between gap-4 border-b border-[#e4dcd0] px-6 py-3">
        <div className="flex items-baseline gap-4">
          <Link href="/author" className="font-[family-name:var(--desk-serif)] text-2xl">
            PreSearch
          </Link>
          <p className="text-[11px] tracking-[0.16em] text-[#6b645c]">AUTHOR DESK</p>
        </div>
        <div className="flex items-center gap-4 text-xs">
          <Link href="/desk" className="underline decoration-[#c4a15a] underline-offset-4">
            Conference desk
          </Link>
          {user ? (
            <form action={signOut}>
              <button className="underline decoration-[#c4a15a] underline-offset-4" type="submit">
                Sign out
              </button>
            </form>
          ) : null}
        </div>
      </header>
      <div className="flex min-h-0 flex-1 flex-col">{children}</div>
      <VoiceDesk />
    </div>
  );
}
