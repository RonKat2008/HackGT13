import { DeskChrome } from "./chrome";
import "./motion.css";

export const metadata = {
  title: "ArxAudit",
  description: "Conference desk for fabricated claims.",
};

export default function DeskLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-dvh w-full flex-col overflow-hidden [font-family:'IBM_Plex_Sans',ui-sans-serif,system-ui,sans-serif]">
      <link
        rel="stylesheet"
        href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=Newsreader:opsz,wght@6..72,400;500;600&display=swap"
      />
      <style>{`html, body { background: #f4f0e6; height: 100%; } :root { --desk-serif: "Newsreader", ui-serif, Georgia, serif; }`}</style>
      <DeskChrome>{children}</DeskChrome>
    </div>
  );
}
