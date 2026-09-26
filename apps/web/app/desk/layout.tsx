import { IBM_Plex_Sans, Newsreader } from "next/font/google";
import { DeskChrome } from "./chrome";
import "./motion.css";

const sans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

const serif = Newsreader({
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata = {
  title: "ArxAudit",
  description: "Conference desk for fabricated claims.",
};

export default function DeskLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className={`${sans.className} flex h-dvh w-full flex-col overflow-hidden`}>
      <style>{`html, body { background: #f4f0e6; height: 100%; } :root { --desk-serif: ${serif.style.fontFamily}; }`}</style>
      <DeskChrome>{children}</DeskChrome>
    </div>
  );
}
