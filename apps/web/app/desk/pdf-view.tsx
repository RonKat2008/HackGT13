"use client";

import { useEffect, useRef, useState } from "react";

type PdfModule = typeof import("pdfjs-dist");

export function PdfView({
  jobId,
  page,
  quote,
}: {
  jobId: string;
  page: number | null;
  quote: string;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [miss, setMiss] = useState(false);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let cancelled = false;

    async function draw() {
      setStatus("loading");
      setMiss(false);
      host!.replaceChildren();
      const pdfjs: PdfModule = await import("pdfjs-dist");
      pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";
      const response = await fetch(`/api/desk/papers/${jobId}/pdf`);
      if (!response.ok) throw new Error("missing pdf");
      const data = new Uint8Array(await response.arrayBuffer());
      if (cancelled) return;
      const doc = await pdfjs.getDocument({ data }).promise;
      if (cancelled) return;
      const width = Math.max(280, host!.clientWidth - 32);
      for (let number = 1; number <= doc.numPages; number += 1) {
        if (cancelled) return;
        const pdfPage = await doc.getPage(number);
        const unscaled = pdfPage.getViewport({ scale: 1 });
        const viewport = pdfPage.getViewport({
          scale: Math.min(1.5, width / unscaled.width),
        });
        const pageEl = document.createElement("div");
        pageEl.className = "pdf-page";
        pageEl.dataset.page = String(number);
        pageEl.style.width = `${viewport.width}px`;
        pageEl.style.height = `${viewport.height}px`;
        const canvas = document.createElement("canvas");
        const context = canvas.getContext("2d");
        if (!context) continue;
        const ratio = window.devicePixelRatio || 1;
        canvas.width = Math.floor(viewport.width * ratio);
        canvas.height = Math.floor(viewport.height * ratio);
        canvas.style.width = `${viewport.width}px`;
        canvas.style.height = `${viewport.height}px`;
        const textLayerDiv = document.createElement("div");
        textLayerDiv.className = "textLayer";
        pageEl.append(canvas, textLayerDiv);
        host!.appendChild(pageEl);
        await pdfPage.render({
          canvasContext: context,
          viewport,
          transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0],
        }).promise;
        if (cancelled) return;
        await new pdfjs.TextLayer({
          textContentSource: pdfPage.streamTextContent(),
          container: textLayerDiv,
          viewport,
        }).render();
      }
      if (cancelled) return;
      const found = markQuote(host!, page, quote);
      setMiss(quote.trim().length >= 4 && !found);
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      const targetNumber = found ? page : quote.trim() ? 1 : page;
      const target =
        host!.querySelector<HTMLElement>(`[data-page="${targetNumber || 1}"]`) ??
        host!.querySelector<HTMLElement>(".pdf-page");
      target?.scrollIntoView({ block: "start", behavior: reduce ? "auto" : "smooth" });
      setStatus("ready");
    }

    draw().catch(() => {
      if (!cancelled) setStatus("error");
    });
    return () => {
      cancelled = true;
    };
  }, [jobId, page, quote]);

  return (
    <div className="flex h-full min-h-0 flex-col bg-[#ebe4d6]">
      {status === "error" ? (
        <p className="px-4 py-6 text-sm text-[#8c3a2f]">The PDF could not be opened.</p>
      ) : null}
      {miss ? (
        <p className="border-b border-[#e4dcd0] bg-[#f4f0e6] px-4 py-2 text-xs leading-5 text-[#6b645c]">
          The clipping is not on that page, so this opens at the start of the PDF.
        </p>
      ) : null}
      <div ref={hostRef} className="min-h-0 flex-1 overflow-auto px-3 py-4" />
      {status === "loading" ? (
        <p className="px-4 pb-3 text-xs text-[#6b645c]">Opening the PDF…</p>
      ) : null}
    </div>
  );
}

function markQuote(root: HTMLElement, page: number | null, quote: string): boolean {
  root.querySelectorAll(".pdf-band").forEach((node) => node.remove());
  const needle = quote.replace(/\s+/g, "").toLowerCase();
  if (needle.length < 4) return false;
  const pageEl = root.querySelector<HTMLElement>(`[data-page="${page && page > 0 ? page : 1}"]`);
  if (!pageEl) return false;
  const layer = pageEl.querySelector(".textLayer");
  if (!layer) return false;
  const nodes: { node: Text; offset: number }[] = [];
  let flat = "";
  layer.querySelectorAll("span").forEach((span) => {
    const textNode = [...span.childNodes].find((node): node is Text => node.nodeType === Node.TEXT_NODE);
    if (!textNode) return;
    const raw = textNode.textContent ?? "";
    for (let index = 0; index < raw.length; index += 1) {
      if (/\s/.test(raw[index] ?? "")) continue;
      nodes.push({ node: textNode, offset: index });
      flat += (raw[index] ?? "").toLowerCase();
    }
  });
  const at = flat.indexOf(needle.slice(0, Math.min(needle.length, 48)));
  if (at < 0 || !nodes[at]) return false;
  const last = nodes[Math.min(nodes.length, at + Math.min(needle.length, 80)) - 1];
  if (!last) return false;
  const range = document.createRange();
  range.setStart(nodes[at].node, nodes[at].offset);
  range.setEnd(last.node, last.offset + 1);
  const pageRect = pageEl.getBoundingClientRect();
  let placed = false;
  for (const rect of range.getClientRects()) {
    if (rect.width < 0.5 || rect.height < 0.5) continue;
    const mark = document.createElement("div");
    mark.className = "pdf-band";
    mark.style.left = `${rect.left - pageRect.left}px`;
    mark.style.top = `${rect.top - pageRect.top}px`;
    mark.style.width = `${rect.width}px`;
    mark.style.height = `${rect.height}px`;
    pageEl.appendChild(mark);
    placed = true;
  }
  return placed;
}
