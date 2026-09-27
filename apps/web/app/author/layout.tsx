export const metadata = {
  title: "ArxAudit — Author",
  description: "Read one paper and ask about what the audit found.",
};

export default function AuthorLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col bg-[#f4f0e6] text-[#1c1915] [font-family:'IBM_Plex_Sans',ui-sans-serif,system-ui,sans-serif]">
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
      {children}
    </div>
  );
}
