export function ReportBody({ markdown }: { markdown: string }) {
  const blocks = markdown.trim().split(/\n{2,}/);
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 font-[family-name:var(--desk-serif)] text-[17px] leading-8 text-[#1c1915]">
      {blocks.map((block) => {
        const lines = block.split("\n");
        const first = lines[0] ?? "";
        if (first.startsWith("### ")) {
          return (
            <h3 key={block} className="text-xl">
              {first.slice(4)}
            </h3>
          );
        }
        if (first.startsWith("## ")) {
          return (
            <h2 key={block} className="mt-4 text-2xl">
              {first.slice(3)}
            </h2>
          );
        }
        if (first.startsWith("# ")) {
          return (
            <h1 key={block} className="text-4xl leading-tight">
              {first.slice(2)}
            </h1>
          );
        }
        if (lines.every((line) => line.startsWith("- "))) {
          return (
            <ul key={block} className="flex flex-col gap-2 font-sans text-sm leading-6">
              {lines.map((line) => (
                <li key={line}>{line.slice(2)}</li>
              ))}
            </ul>
          );
        }
        if (first.startsWith("```")) {
          const code = lines.slice(1, lines.at(-1) === "```" ? -1 : undefined).join("\n");
          return (
            <pre key={block} className="overflow-x-auto bg-white px-4 py-3 font-mono text-xs leading-5">
              {code}
            </pre>
          );
        }
        return (
          <p key={block} className="whitespace-pre-wrap">
            {block}
          </p>
        );
      })}
    </div>
  );
}
