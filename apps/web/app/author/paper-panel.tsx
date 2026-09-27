"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import type { Paper, Quote, TraceStep } from "@/lib/desk";
import { PdfView } from "../desk/pdf-view";
import { ChatReply } from "../desk/reply";

const CHIPS = [
  "what to fix first",
  "which citation failed",
  "whether the abstract number is in the results",
  "what still needs a person",
  "explain the formula",
  "what passed",
] as const;

type ShelfItem = {
  job_id: string;
  arxiv_id: string;
  title: string;
  status: string;
};

type AskAction = {
  type: "refuse" | "explain" | "open" | "list";
  [key: string]: unknown;
};

type Message = {
  role: "you" | "desk";
  text: string;
  quotes?: Quote[];
};

type Started = {
  job_id: string;
  arxiv_id: string;
  title: string;
  status: string;
};

function errorText(body: unknown, fallback: string): string {
  if (body && typeof body === "object") {
    const record = body as { detail?: unknown; error?: unknown };
    if (typeof record.detail === "string" && record.detail.trim()) return record.detail;
    if (typeof record.error === "string" && record.error.trim()) return record.error;
  }
  return fallback;
}

function statusClass(status: string): string {
  return status === "contradicted" ? "text-[#8c3a2f]" : "text-[#1c1915]";
}

export function PaperPanel() {
  const [shelf, setShelf] = useState<ShelfItem[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const [paper, setPaper] = useState<Paper | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [booting, setBooting] = useState(true);
  const [focusPage, setFocusPage] = useState<number | null>(null);
  const [focusText, setFocusText] = useState("");
  const [focusToken, setFocusToken] = useState(0);
  const [pdfOpen, setPdfOpen] = useState(false);
  const threadRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const response = await fetch("/api/author/papers");
        if (!response.ok) {
          if (!cancelled) setBooting(false);
          return;
        }
        const body = (await response.json()) as { papers?: ShelfItem[] };
        const papers = Array.isArray(body.papers) ? body.papers : [];
        if (cancelled) return;
        setShelf(papers);
        if (papers.length > 0) {
          setJobId(papers[papers.length - 1]!.job_id);
        }
      } finally {
        if (!cancelled) setBooting(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!jobId) {
      setPaper(null);
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setPaper(null);

    async function poll() {
      const response = await fetch(`/api/author/papers/${jobId}`);
      if (cancelled || !response.ok) return;
      const next = (await response.json()) as Paper;
      if (cancelled) return;
      setPaper(next);
      setShelf((current) =>
        current.map((item) =>
          item.job_id === next.job_id
            ? {
                ...item,
                title: next.title || item.title,
                arxiv_id: next.arxiv_id || item.arxiv_id,
                status: next.status,
              }
            : item,
        ),
      );
      if (next.status === "queued" || next.status === "running") {
        timer = setTimeout(() => {
          void poll();
        }, 2000);
      }
    }

    void poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [jobId]);

  useEffect(() => {
    if (!jobId) {
      setMessages([]);
      return;
    }
    let cancelled = false;
    void (async () => {
      const response = await fetch(`/api/author/papers/${jobId}/messages`);
      if (!response.ok || cancelled) return;
      const body = (await response.json()) as { messages?: Message[] };
      if (cancelled || !Array.isArray(body.messages)) return;
      setMessages(body.messages);
    })();
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  useEffect(() => {
    const node = threadRef.current;
    if (!node) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    node.scrollTo({ top: node.scrollHeight, behavior: reduce ? "auto" : "smooth" });
  }, [messages, busy]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const arxiv = String(data.get("arxiv_id") ?? "").trim();
    const file = data.get("pdf");
    const hasFile = file instanceof File && file.size > 0;
    if (!arxiv && !hasFile) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      let response: Response;
      if (hasFile) {
        const form = new FormData();
        form.append("pdf", file);
        response = await fetch("/api/author/papers", { method: "POST", body: form });
      } else {
        response = await fetch("/api/author/papers", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ arxiv_id: arxiv }),
        });
      }
      const body = (await response.json().catch(() => ({}))) as Started & {
        detail?: string;
        error?: string;
      };
      if (!response.ok) {
        setSubmitError(errorText(body, "Could not open the paper."));
        return;
      }
      const started: ShelfItem = {
        job_id: body.job_id,
        arxiv_id: body.arxiv_id,
        title: body.title || body.arxiv_id,
        status: body.status,
      };
      setShelf((current) => {
        if (current.some((item) => item.job_id === started.job_id)) return current;
        return [...current, started];
      });
      setJobId(started.job_id);
      setPdfOpen(false);
      setFocusPage(null);
      setFocusText("");
    } catch {
      setSubmitError("Could not open the paper.");
    } finally {
      setSubmitting(false);
    }
  }

  async function send(text?: string) {
    if (!jobId) return;
    const question = (text ?? draft).trim();
    if (!question || busy) return;
    setMessages((current) => [...current, { role: "you", text: question }]);
    setDraft("");
    setBusy(true);
    try {
      const response = await fetch(`/api/author/papers/${jobId}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      const body = (await response.json()) as {
        answer?: string;
        quotes?: Quote[];
        trace?: TraceStep[];
        action?: AskAction | null;
      };
      setMessages((current) => [
        ...current,
        {
          role: "desk",
          text: body.answer || "The desk could not answer that.",
          quotes: body.quotes ?? [],
        },
      ]);
    } catch {
      setMessages((current) => [
        ...current,
        { role: "desk", text: "The desk could not answer that." },
      ]);
    } finally {
      setBusy(false);
    }
  }

  function openQuote(quote: Quote) {
    setFocusPage(typeof quote.page === "number" ? quote.page : null);
    setFocusText(quote.text || "");
    setFocusToken((token) => token + 1);
    setPdfOpen(true);
  }

  if (booting) {
    return (
      <div className="flex flex-1 items-center justify-center px-6 py-16 text-sm text-[#6b645c]">
        Opening your shelf…
      </div>
    );
  }

  if (!jobId) {
    return (
      <div className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-6 py-16">
        <form onSubmit={onSubmit} className="flex flex-col gap-5">
          <div>
            <p className="text-[11px] tracking-[0.18em] text-[#8c3a2f]">FOR AUTHORS</p>
            <h1 className="mt-3 font-[family-name:var(--desk-serif)] text-4xl leading-tight text-[#1c1915]">
              One paper, one read.
            </h1>
            <p className="mt-3 text-sm leading-6 text-[#6b645c]">
              Paste an arXiv id or upload a PDF. The audit runs on that paper alone.
            </p>
          </div>
          <label className="flex flex-col gap-1 text-sm text-[#1c1915]">
            arXiv id
            <input
              name="arxiv_id"
              type="text"
              placeholder="2503.18421"
              autoComplete="off"
              className="rounded-2xl bg-white px-4 py-3 outline-none ring-[#e4dcd0] focus-visible:ring-2"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-[#1c1915]">
            PDF
            <input
              name="pdf"
              type="file"
              accept="application/pdf,.pdf"
              className="text-sm text-[#6b645c] file:mr-3 file:rounded-full file:border-0 file:bg-[#1c1915] file:px-4 file:py-2 file:text-sm file:text-[#f4f0e6]"
            />
          </label>
          {submitError ? <p className="text-sm text-[#8c3a2f]">{submitError}</p> : null}
          <button
            type="submit"
            disabled={submitting}
            className="w-fit rounded-full bg-[#1c1915] px-5 py-3 text-sm text-[#f4f0e6] disabled:opacity-60"
          >
            {submitting ? "Opening…" : "Open the paper"}
          </button>
        </form>
      </div>
    );
  }

  if (!paper) {
    return (
      <div className="flex flex-1 items-center justify-center px-6 py-16 text-sm text-[#6b645c]">
        Loading the paper…
      </div>
    );
  }

  const running = paper.status === "queued" || paper.status === "running";
  const findings = paper.finding_count;

  return (
    <div className="author-thread flex min-h-0 flex-1 flex-col">
      <header className="shrink-0 border-b border-[#e4dcd0] px-6 py-4">
        <div className="mx-auto flex max-w-6xl flex-col gap-3">
          {shelf.length > 1 ? (
            <nav aria-label="Your papers" className="flex flex-wrap gap-2">
              {shelf.map((item) => {
                const active = item.job_id === jobId;
                return (
                  <button
                    key={item.job_id}
                    type="button"
                    onClick={() => {
                      setJobId(item.job_id);
                      setPdfOpen(false);
                      setFocusPage(null);
                      setFocusText("");
                    }}
                    className={`max-w-[14rem] truncate rounded-full px-3 py-1.5 text-left text-xs ${
                      active
                        ? "bg-[#1c1915] text-[#f4f0e6]"
                        : "bg-white text-[#6b645c] ring-1 ring-[#e4dcd0]"
                    }`}
                  >
                    {item.title || item.arxiv_id}
                  </button>
                );
              })}
            </nav>
          ) : null}
          <article className="border-l-2 border-[#c4a15a] pl-4">
            <p className="text-[11px] tracking-[0.16em] text-[#6b645c]">{paper.arxiv_id}</p>
            <h1 className="mt-1 font-[family-name:var(--desk-serif)] text-2xl leading-tight text-[#1c1915] min-[960px]:text-3xl">
              {paper.title || "Unread paper"}
            </h1>
            <div className="mt-2 flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm">
              <span className={statusClass(paper.status)}>{paper.status}</span>
              {typeof findings === "number" ? (
                <span className="text-[#6b645c]">
                  {findings} {findings === 1 ? "finding" : "findings"}
                </span>
              ) : null}
              {running && paper.specialist ? (
                <span className="text-[#6b645c]">pass: {paper.specialist}</span>
              ) : null}
            </div>
          </article>
        </div>
      </header>

      <div
        className={`mx-auto flex min-h-0 w-full max-w-6xl flex-1 flex-col ${
          pdfOpen ? "min-[960px]:flex-row" : ""
        }`}
      >
        <section className="relative flex min-h-0 min-w-0 flex-1 flex-col">
          <div ref={threadRef} className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
            <div className="mx-auto flex min-h-full w-full max-w-2xl flex-col">
              {messages.length === 0 ? (
                <div className="flex flex-1 flex-col justify-center">
                  <h2 className="font-[family-name:var(--desk-serif)] text-4xl leading-tight text-[#1c1915]">
                    Ask about this paper
                  </h2>
                  <p className="mt-3 max-w-md text-sm leading-6 text-[#6b645c]">
                    The thread stays on this read. Ask what failed, what passed, or what still needs
                    a person.
                  </p>
                </div>
              ) : (
                <div className="flex flex-col gap-6">
                  {messages.map((turn, index) =>
                    turn.role === "you" ? (
                      <article key={`you-${index}`} className="flex justify-end">
                        <p className="max-w-[80%] rounded-3xl bg-[#1c1915] px-4 py-3 text-sm leading-6 text-[#f4f0e6]">
                          {turn.text}
                        </p>
                      </article>
                    ) : (
                      <ChatReply
                        key={`desk-${index}`}
                        text={turn.text}
                        quotes={turn.quotes ?? []}
                        papers={[paper]}
                        citedIds={[paper.arxiv_id]}
                        trace={[]}
                        layout="findings"
                        activeQuoteId=""
                        onOpenQuote={(quote) => openQuote(quote)}
                        onOpenPaper={() => {
                          const issue = paper.issues[0];
                          setFocusPage(typeof issue?.page === "number" ? issue.page : 1);
                          setFocusText(issue?.evidence_span || issue?.claim_text || "");
                          setFocusToken((token) => token + 1);
                          setPdfOpen(true);
                        }}
                      />
                    ),
                  )}
                  {busy ? (
                    <p className="text-sm text-[#6b645c]" aria-live="polite">
                      Reading…
                    </p>
                  ) : null}
                </div>
              )}
            </div>
          </div>

          <div className="shrink-0 border-t border-[#e4dcd0] bg-[#f4f0e6] px-6 pb-5 pt-3">
            <div className="mx-auto w-full max-w-2xl">
              <div className="mb-3 flex flex-wrap gap-2">
                {CHIPS.map((label) => (
                  <button
                    key={label}
                    type="button"
                    onClick={() => void send(label)}
                    className="rounded-full bg-white px-3 py-1.5 text-xs text-[#1c1915] ring-1 ring-[#e4dcd0] hover:bg-[#faf7f0]"
                  >
                    {label}
                  </button>
                ))}
              </div>
              <form
                className="flex items-end gap-2 rounded-2xl bg-white px-4 py-3 ring-1 ring-[#e4dcd0]"
                onSubmit={(event) => {
                  event.preventDefault();
                  void send();
                }}
              >
                <label className="sr-only" htmlFor="author-ask">
                  Ask about this paper
                </label>
                <textarea
                  id="author-ask"
                  value={draft}
                  rows={1}
                  placeholder="Ask about this paper"
                  onChange={(event) => {
                    setDraft(event.target.value);
                    event.currentTarget.style.height = "auto";
                    event.currentTarget.style.height = `${Math.min(event.currentTarget.scrollHeight, 120)}px`;
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      void send();
                    }
                  }}
                  className="min-h-[1.5rem] max-h-[7.5rem] min-w-0 flex-1 resize-none bg-transparent text-sm leading-6 outline-none"
                />
                <button
                  type="submit"
                  disabled={busy || !draft.trim()}
                  className="shrink-0 rounded-full bg-[#1c1915] px-4 py-2 text-sm text-[#f4f0e6] disabled:opacity-40"
                >
                  Send
                </button>
              </form>
            </div>
          </div>
        </section>

        {pdfOpen ? (
          <aside className="flex min-h-[50vh] min-w-0 flex-col border-t border-[#e4dcd0] min-[960px]:min-h-0 min-[960px]:w-[min(42%,28rem)] min-[960px]:border-l min-[960px]:border-t-0">
            <div className="flex items-center justify-between border-b border-[#e4dcd0] px-4 py-3">
              <p className="text-xs tracking-[0.14em] text-[#6b645c]">PDF</p>
              <button
                type="button"
                onClick={() => setPdfOpen(false)}
                className="text-xs text-[#6b645c] hover:text-[#1c1915]"
              >
                Close
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-auto p-3">
              <PdfView
                jobId={jobId}
                focusPage={focusPage}
                focusText={focusText}
                focusToken={focusToken}
              />
            </div>
          </aside>
        ) : null}
      </div>
    </div>
  );
}
