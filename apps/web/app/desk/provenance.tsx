import type { Claim } from "@/lib/desk";
import { claimVerdictLabel, isFinding, percent } from "@/lib/verdict";

const CATALOG_NAME: Record<string, string> = {
  crossref: "Crossref",
  openalex: "OpenAlex",
  semantic_scholar: "Semantic Scholar",
};

const INK = "#1c1915";
const RULE = "#e4dcd0";
const CREAM = "#f4f0e6";
const GOLD = "#c4a15a";
const RUST = "#8c3a2f";
const GREEN = "#2f6b4f";

type ChainNode = {
  label: string;
  lines: string[];
};

type ChainEdge = {
  label: string;
};

function evidenceNodeLabel(source: string, page: number | null): string {
  if (source === "paper") return page != null ? `Paper p.${page}` : "Paper";
  if (source === "catalog") return "Catalog";
  if (source === "dataset") return "Dataset";
  if (source === "computation") return "Computation";
  return source;
}

function evidenceEdgeLabel(role: string): string {
  if (role === "contradicts") return "contradicts";
  if (role === "context") return "context";
  return "supports";
}

function textWidth(text: string, size: number): number {
  return Math.ceil(text.length * size * 0.58);
}

function nodeWidth(node: ChainNode): number {
  const sizes = [10, 9, 9];
  const widths = node.lines.map((line, i) => textWidth(line, sizes[i] ?? 9));
  return Math.max(56, ...widths) + 16;
}

function nodeFill(kind: "mid" | "jev", verdict: string): string {
  if (kind !== "jev") return "#fffef9";
  if (verdict === "supported" || verdict === "reproduced") return "#eef5f0";
  if (
    verdict === "contradicted" ||
    verdict === "unresolved" ||
    verdict === "could_not_reproduce" ||
    verdict === "insufficient_evidence"
  ) {
    return "#f7efec";
  }
  return "#fffef9";
}

function nodeStroke(kind: "mid" | "jev", verdict: string): string {
  if (kind !== "jev") return RULE;
  if (verdict === "supported" || verdict === "reproduced") return GREEN;
  if (
    verdict === "contradicted" ||
    verdict === "unresolved" ||
    verdict === "could_not_reproduce" ||
    verdict === "insufficient_evidence"
  ) {
    return RUST;
  }
  return GOLD;
}

export function Provenance({ claim }: { claim: Claim }) {
  if (!isFinding(claim)) return null;

  const nodes: ChainNode[] = [
    {
      label: "claim",
      lines: [claim.page != null ? `Claim p.${claim.page}` : "Claim"],
    },
  ];
  const edges: ChainEdge[] = [];

  for (const item of claim.evidence) {
    nodes.push({
      label: "evidence",
      lines: [evidenceNodeLabel(item.source, item.page)],
    });
    edges.push({ label: evidenceEdgeLabel(item.role) });
  }

  for (const row of claim.catalog?.queried ?? []) {
    nodes.push({
      label: "catalog",
      lines: [CATALOG_NAME[row.catalog] ?? row.catalog],
    });
    edges.push({ label: "resolves_to" });
  }

  if (claim.computation) {
    nodes.push({ label: "computation", lines: ["Computation"] });
    edges.push({ label: "computed_from" });
  }

  nodes.push({
    label: "jev",
    lines: ["Jev", claimVerdictLabel(claim.verdict), percent(claim.confidence)],
  });
  edges.push({ label: "" });

  const widths = nodes.map(nodeWidth);
  const gap = 52;
  const padX = 10;
  const padY = 10;
  const nodeH = (node: ChainNode) => (node.lines.length > 1 ? 48 : 28);
  const maxH = Math.max(...nodes.map(nodeH));
  const totalW = padX * 2 + widths.reduce((a, b) => a + b, 0) + gap * (nodes.length - 1);
  const totalH = padY * 2 + maxH + 14;

  const xs: number[] = [];
  let x = padX;
  for (const w of widths) {
    xs.push(x);
    x += w + gap;
  }

  const cy = padY + maxH / 2;
  const aria = nodes.map((n) => n.lines.join(" ")).join(" → ");

  return (
    <svg
      viewBox={`0 0 ${totalW} ${totalH}`}
      width="100%"
      role="img"
      aria-label={`Evidence chain: ${aria}`}
      style={{ display: "block", marginTop: 12, maxWidth: totalW }}
    >
      <rect x={0} y={0} width={totalW} height={totalH} fill={CREAM} rx={6} />
      {edges.map((edge, i) => {
        const x1 = xs[i]! + widths[i]!;
        const x2 = xs[i + 1]!;
        const mid = (x1 + x2) / 2;
        return (
          <g key={`e-${i}`}>
            <line x1={x1} y1={cy} x2={x2} y2={cy} stroke={GOLD} strokeWidth={1.25} />
            <polygon
              points={`${x2},${cy} ${x2 - 5},${cy - 3.5} ${x2 - 5},${cy + 3.5}`}
              fill={GOLD}
            />
            {edge.label ? (
              <text
                x={mid}
                y={cy - 6}
                textAnchor="middle"
                fill={INK}
                fontSize={8}
                fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
              >
                {edge.label}
              </text>
            ) : null}
          </g>
        );
      })}
      {nodes.map((node, i) => {
        const w = widths[i]!;
        const h = nodeH(node);
        const nx = xs[i]!;
        const ny = cy - h / 2;
        const kind = node.label === "jev" ? "jev" : "mid";
        const lineGap = node.lines.length > 1 ? 12 : 0;
        const startY = cy - ((node.lines.length - 1) * lineGap) / 2 + 3;
        return (
          <g key={`n-${i}`}>
            <rect
              x={nx}
              y={ny}
              width={w}
              height={h}
              rx={5}
              fill={nodeFill(kind, claim.verdict)}
              stroke={nodeStroke(kind, claim.verdict)}
              strokeWidth={1}
            />
            {node.lines.map((line, li) => (
              <text
                key={li}
                x={nx + w / 2}
                y={startY + li * lineGap}
                textAnchor="middle"
                fill={li === 1 && kind === "jev" ? nodeStroke("jev", claim.verdict) : INK}
                fontSize={li === 0 ? 10 : 9}
                fontWeight={li === 0 ? 600 : 400}
                fontFamily="ui-sans-serif, system-ui, sans-serif"
              >
                {line}
              </text>
            ))}
          </g>
        );
      })}
    </svg>
  );
}
