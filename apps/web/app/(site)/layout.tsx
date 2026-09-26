import { SiteNav } from "./nav";
import "./site.css";

export default function SiteLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-dvh bg-[#f4f0e6] text-[#1c1915] [font-family:'IBM_Plex_Sans',ui-sans-serif,system-ui,sans-serif]">
      <link
        rel="stylesheet"
        href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=Newsreader:opsz,wght@6..72,400;500;600&display=swap"
      />
      <style>{`:root { --desk-serif: "Newsreader", ui-serif, Georgia, serif; } body { background: #f4f0e6; color: #1c1915; }`}</style>
      <SiteNav />
      {children}
    </div>
  );
}
