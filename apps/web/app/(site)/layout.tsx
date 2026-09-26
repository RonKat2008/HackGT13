import { IBM_Plex_Sans, Newsreader } from "next/font/google";
import { SiteNav } from "./nav";
import "./site.css";

const sans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

const serif = Newsreader({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

export default function SiteLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className={`${sans.className} min-h-dvh bg-[#f4f0e6] text-[#1c1915]`}>
      <style>{`:root { --desk-serif: ${serif.style.fontFamily}; } body { background: #f4f0e6; color: #1c1915; }`}</style>
      <SiteNav />
      {children}
    </div>
  );
}
