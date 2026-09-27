"use client";

import { useEffect, useRef, useState } from "react";

type PdfModule = typeof import("pdfjs-dist");

export type PdfMark = {
  page: number | null;
  text: string;
  role: string;
};

export function PdfView({
  jobId,
  page = null,
  quote = "",
  marks,
  focusPage = null,
  focusText = "",
  focusToken = 0,
}: {
  jobId: string;
  page?: number | null;
  quote?: string;
  marks?: PdfMark[];
  focusPage?: number | null;
  focusText?: string;
  focusToken?: number;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [miss, setMiss] = useState(false);
  const [pageNow, setPageNow] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const markKey = JSON.stringify(marks ?? null);

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
      host!.querySelectorAll(".pdf-band").forEach((node) => node.remove());
      const parsed = JSON.parse(markKey) as PdfMark[] | null;
      const drawn = (parsed && parsed.length > 0 ? parsed : [{ page, text: quote, role: "claim" }]).filter(
        (mark) => mark.text.trim().length >= 4,
      );
      let found = false;
      for (const mark of drawn) {
        if (markQuote(host!, mark.page, mark.text, mark.role)) found = true;
      }
      setMiss(drawn.length > 0 && !found);
      scrollToQuote(host!, focusPage, focusText);
      notePage(host!, setPageNow, setPageCount);
      setStatus("ready");
    }

    draw().catch(() => {
      if (!cancelled) setStatus("error");
    });
    return () => {
      cancelled = true;
    };
  }, [jobId, page, quote, markKey, focusPage, focusText]);

  useEffect(() => {
    if (!focusToken) return;
    const host = hostRef.current;
    if (!host) return;
    scrollToQuote(host, focusPage, focusText);
  }, [focusToken, focusPage, focusText]);

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
      <div className="relative min-h-0 flex-1">
        <div
          ref={hostRef}
          onScroll={() => {
            if (hostRef.current) notePage(hostRef.current, setPageNow, setPageCount);
          }}
          className="h-full min-h-0 overflow-auto px-3 py-4"
        />
        {pageCount > 0 ? (
          <p className="pointer-events-none absolute right-3 bottom-3 rounded-full bg-[#f4f0e6]/90 px-2 py-1 text-[11px] text-[#1c1915] ring-1 ring-[#e4dcd0]">
            Page {pageNow} of {pageCount}
          </p>
        ) : null}
      </div>
      {status === "loading" ? (
        <p className="px-4 pb-3 text-xs text-[#6b645c]">Opening the PDF…</p>
      ) : null}
    </div>
  );
}

function notePage(
  root: HTMLElement,
  setNow: (page: number) => void,
  setCount: (count: number) => void,
): void {
  const pages = [...root.querySelectorAll<HTMLElement>(".pdf-page")];
  if (!pages.length) return;
  const box = root.getBoundingClientRect();
  let current = 1;
  for (const node of pages) {
    const rect = node.getBoundingClientRect();
    if (rect.top <= box.top + box.height * 0.35) {
      current = Number(node.dataset.page || 1);
    }
  }
  setNow(current);
  setCount(pages.length);
}

function scrollToQuote(root: HTMLElement, page: number | null, quote: string): void {
  const needle = quote.replace(/\s+/g, "").toLowerCase().slice(0, 24);
  const bands = [...root.querySelectorAll<HTMLElement>(".pdf-band")];
  const onPage = page ? root.querySelector<HTMLElement>(`[data-page="${page}"]`) : null;
  const match =
    bands.find((band) => needle.length >= 8 && (band.dataset.quote ?? "").startsWith(needle.slice(0, 12))) ??
    onPage?.querySelector<HTMLElement>(".pdf-band") ??
    bands[0] ??
    onPage ??
    root.querySelector<HTMLElement>(".pdf-page");
  if (!match) return;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  match.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
}

function markQuote(root: HTMLElement, page: number | null, quote: string, role: string): boolean {
  const full = quote.replace(/\s+/g, "").toLowerCase();
  const words = quote
    .replace(/\s+/g, " ")
    .trim()
    .split(" ")
    .slice(0, 6)
    .join("")
    .toLowerCase();
  const number = quote.match(/\d+\.\d+/)?.[0] ?? "";
  const needles = [full.slice(0, 48), words, number].filter((item) => item.length >= 4);
  for (const needle of needles) {
    if (placeBand(root, page, needle, role, needle.length)) return true;
  }
  return false;
}

function placeBand(root: HTMLElement, page: number | null, needle: string, role: string, span: number): boolean {
  const pages = [...root.querySelectorAll<HTMLElement>(".pdf-page")];
  const preferred = root.querySelector<HTMLElement>(`[data-page="${page && page > 0 ? page : 1}"]`);
  const ordered = preferred ? [preferred, ...pages.filter((item) => item !== preferred)] : pages;
  for (const pageEl of ordered) {
    if (placeOnPage(pageEl, needle, role, span)) return true;
  }
  return false;
}

function placeOnPage(pageEl: HTMLElement, needle: string, role: string, span: number): boolean {
  const layer = pageEl.querySelector(".textLayer");
  if (!layer) return false;
  const nodes: { node: Text; offset: number }[] = [];
  let flat = "";
  layer.querySelectorAll("span").forEach((item) => {
    const textNode = [...item.childNodes].find((node): node is Text => node.nodeType === Node.TEXT_NODE);
    if (!textNode) return;
    const raw = textNode.textContent ?? "";
    for (let index = 0; index < raw.length; index += 1) {
      if (/\s/.test(raw[index] ?? "")) continue;
      nodes.push({ node: textNode, offset: index });
      flat += (raw[index] ?? "").toLowerCase();
    }
  });
  const at = flat.indexOf(needle);
  if (at < 0 || !nodes[at]) return false;
  const last = nodes[Math.min(nodes.length, at + Math.min(span, 80)) - 1];
  if (!last) return false;
  const range = document.createRange();
  range.setStart(nodes[at].node, nodes[at].offset);
  range.setEnd(last.node, last.offset + 1);
  const pageRect = pageEl.getBoundingClientRect();
  let placed = false;
  for (const rect of range.getClientRects()) {
    if (rect.width < 0.5 || rect.height < 0.5) continue;
    const mark = document.createElement("div");
    mark.className = role === "contradicts" ? "pdf-band pdf-band-contradicts" : "pdf-band";
    mark.dataset.role = role;
    mark.dataset.quote = needle.slice(0, 24);
    mark.style.left = `${rect.left - pageRect.left}px`;
    mark.style.top = `${rect.top - pageRect.top}px`;
    mark.style.width = `${rect.width}px`;
    mark.style.height = `${rect.height}px`;
    pageEl.appendChild(mark);
    placed = true;
  }
  return placed;
}
