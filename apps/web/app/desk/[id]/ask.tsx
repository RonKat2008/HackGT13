"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { Paper, Quote, TraceStep } from "@/lib/desk";
import type { DeskVoiceAction } from "../voice-action";
import { takeChatPrompt } from "../voice-action";
import { MorphLink } from "../morph-link";
import { PdfView } from "../pdf-view";
import { ChatReply, issueLabel } from "../reply";

type YouTurn = { role: "you"; text: string };
type DeskAction = {
  type: "open" | "explain" | "list" | "refuse";
  job_id?: string;
  arxiv_id?: string;
  title?: string;
  page?: number | null;
  text?: string;
  formula?: string;
};
type DeskTurn = {
  role: "desk";
  text: string;
  trace: TraceStep[];
  quotes: Quote[];
  papers: string[];
  action?: DeskAction | null;
};
type Turn = YouTurn | DeskTurn;

type Panel =
  | { kind: "quote"; quote: Quote }
  | { kind: "unread"; title: string; abstract: string };

function nameOf(paper: Paper): string {
  return paper.title || "Unread paper";
}

export function AskDesk({
  conferenceId,
  conferenceName,
  papers,
  embedded = false,
  onOpenQuote,
}: {
  conferenceId: string;
  conferenceName: string;
  papers: Paper[];
  embedded?: boolean;
  onOpenQuote?: (quote: Quote) => void;
}) {
  const [draft, setDraft] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [menuOpen, setMenuOpen] = useState(true);
  const [cursor, setCursor] = useState(0);
  const [cursorQuery, setCursorQuery] = useState<string | null>(null);
  const [panel, setPanel] = useState<Panel | null>(null);
  const threadRef = useRef<HTMLDivElement>(null);
  const fieldRef = useRef<HTMLTextAreaElement>(null);
  const markerRef = useRef<HTMLButtonElement | null>(null);
  const query = draft.match(/@([^@\n]*)$/)?.[1] ?? null;
  if (query !== cursorQuery) {
    setCursorQuery(query);
    setCursor(0);
  }
  const matches = useMemo(() => {
    if (query === null) return [];
    const needle = query.trim().toLowerCase();
    return papers
      .filter((paper) => {
        const name = nameOf(paper).toLowerCase();
        return !needle || name.includes(needle) || paper.arxiv_id.includes(needle);
      })
      .slice(0, 8);
  }, [papers, query]);
  const showMenu = menuOpen && matches.length > 0;

  useEffect(() => {
    const node = threadRef.current;
    if (!node) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    node.scrollTo({ top: node.scrollHeight, behavior: reduce ? "auto" : "smooth" });
  }, [turns, busy]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const response = await fetch(`/api/desk/conferences/${conferenceId}/messages`);
      if (!response.ok || cancelled) return;
      const body = (await response.json()) as { messages?: Turn[] };
      if (cancelled || !Array.isArray(body.messages)) return;
      setTurns((current) => (current.length > 0 ? current : body.messages ?? []));
    })();
    return () => {
      cancelled = true;
    };
  }, [conferenceId]);

  const sendRef = useRef<(text?: string) => Promise<void>>(async () => {});

  useEffect(() => {
    const queued = takeChatPrompt();
    if (queued) void sendRef.current(queued);
    function onVoice(event: Event) {
      const action = (event as CustomEvent<DeskVoiceAction>).detail;
      if (action?.type !== "prompt" || !action.text) return;
      takeChatPrompt();
      void sendRef.current(action.text);
    }
    window.addEventListener("desk-voice", onVoice);
    return () => window.removeEventListener("desk-voice", onVoice);
  }, [conferenceId]);

  function pick(paper: Paper) {
    setDraft((current) => current.replace(/@([^@\n]*)$/, `@${nameOf(paper)} `));
    setMenuOpen(false);
    fieldRef.current?.focus();
  }

  function openQuote(quote: Quote, button?: HTMLButtonElement | null) {
    if (button) markerRef.current = button;
    if (onOpenQuote) {
      onOpenQuote(quote);
      return;
    }
    setPanel({ kind: "quote", quote });
  }

  function openPaper(paper: Paper, button?: HTMLButtonElement | null) {
    if (button) markerRef.current = button;
    const unread = !paper.paper_text.trim() && paper.status !== "passed" && paper.status !== "contradicted";
    if (unread) {
      const quote: Quote = {
        quote_id: `unread-${paper.job_id}`,
        job_id: paper.job_id,
        arxiv_id: paper.arxiv_id,
        title: nameOf(paper),
        page: null,
        text: "",
        issue_type: "",
        reason: "",
      };
      if (onOpenQuote) onOpenQuote(quote);
      else setPanel({ kind: "unread", title: nameOf(paper), abstract: paper.abstract });
      return;
    }
    const issue = paper.issues[0];
    openQuote(
      {
        quote_id: issue ? `${paper.job_id}-0` : `open-${paper.job_id}`,
        job_id: paper.job_id,
        arxiv_id: paper.arxiv_id,
        title: nameOf(paper),
        page: typeof issue?.page === "number" ? issue.page : issue ? null : 1,
        text: issue?.evidence_span || issue?.claim_text || "",
        issue_type: issue?.issue_type || "",
        reason: issue?.reason || "",
      },
      button,
    );
  }

  function closePanel() {
    setPanel(null);
    markerRef.current?.focus();
  }

  async function send(text?: string) {
    const question = (text ?? draft).trim();
    if (!question || busy) return;
    const mentions = papers
      .filter((paper) => {
        const name = nameOf(paper);
        return question.includes(`@${name}`) || question.includes(`@${paper.arxiv_id}`);
      })
      .map((paper) => paper.arxiv_id);
    setTurns((current) => [...current, { role: "you", text: question }]);
    setDraft("");
    setMenuOpen(false);
    if (fieldRef.current) fieldRef.current.style.height = "auto";
    setBusy(true);
    try {
      const response = await fetch("/api/desk/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ conferenceId, question, mentions }),
      });
      const body = (await response.json()) as {
        answer?: string;
        trace?: TraceStep[];
        quotes?: Quote[];
        papers?: string[];
        action?: DeskAction | null;
      };
      const action = body.action ?? null;
      setTurns((current) => [
        ...current,
        {
          role: "desk",
          text: body.answer || "The desk could not answer that.",
          trace: body.trace ?? [],
          quotes: body.quotes ?? [],
          papers: body.papers ?? [],
          action,
        },
      ]);
      if (action?.type === "open" && action.job_id) {
        openQuote({
          quote_id: `bot-${action.job_id}`,
          job_id: action.job_id,
          arxiv_id: action.arxiv_id || "",
          title: action.title || "Paper",
          page: typeof action.page === "number" ? action.page : null,
          text: action.text || "",
          issue_type: "",
          reason: "",
        });
      }
    } catch {
      setTurns((current) => [
        ...current,
        { role: "desk", text: "The desk could not answer that.", trace: [], quotes: [], papers: [] },
      ]);
    } finally {
      setBusy(false);
    }
  }

  sendRef.current = send;

  const starters = [
    "List the findings",
    "Open the first finding",
    papers[0] ? `Explain the formula on @${nameOf(papers[0])}` : "Explain the formula",
  ];
  const passageOpen = panel !== null && !onOpenQuote;

  return (
    <section className="relative flex min-h-0 flex-1 flex-col lg:flex-row">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div ref={threadRef} className="min-h-0 flex-1 overflow-y-auto px-6 py-8">
          <div className={`mx-auto flex min-h-full w-full flex-col ${embedded ? "" : "max-w-2xl"}`}>
            {turns.length === 0 ? (
              <div className="flex flex-1 flex-col justify-center">
                <h2 className="font-[family-name:var(--desk-serif)] text-5xl leading-tight">
                  Ask {conferenceName}
                </h2>
                <p className="mt-4 max-w-md text-sm leading-6 text-[#6b645c]">
                  {papers.length} papers in this conversation. Type @ and a paper name to pin a question. The desk can list findings, open a page, and explain a stored formula. It does not change a verdict.
                </p>
                <ul className="mt-8 flex max-w-lg flex-col gap-2">
                  {starters.map((prompt, index) => (
                    <li key={prompt} className="desk-rise" style={{ animationDelay: `${80 + index * 70}ms` }}>
                      <button
                        type="button"
                        onClick={() => void send(prompt)}
                        className="w-full rounded-2xl bg-white px-4 py-3 text-left text-sm leading-6 text-[#1c1915] ring-1 ring-[#e4dcd0] hover:ring-[#c4a15a]"
                      >
                        {prompt}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <div className="flex flex-col gap-7">
                {turns.map((turn, index) =>
                  turn.role === "you" ? (
                    <article key={`you-${index}`} className="desk-rise flex justify-end">
                      <p className="max-w-[80%] rounded-3xl bg-[#1c1915] px-4 py-3 text-sm leading-6 text-[#f4f0e6]">
                        <Message text={turn.text} papers={papers} conferenceId={conferenceId} />
                      </p>
                    </article>
                  ) : (
                    <ChatReply
                      key={`desk-${index}`}
                      text={turn.text}
                      quotes={turn.quotes}
                      papers={papers}
                      citedIds={turn.papers}
                      trace={turn.trace}
                      formula={turn.action?.type === "explain" ? turn.action.formula : undefined}
                      pageAction={turn.action?.type === "open" ? turn.action : null}
                      conferenceId={conferenceId}
                      activeQuoteId={panel?.kind === "quote" ? panel.quote.quote_id : ""}
                      activeJobId={panel?.kind === "quote" ? panel.quote.job_id : ""}
                      onOpenQuote={openQuote}
                      onOpenPaper={openPaper}
                    />
                  ),
                )}
                {busy ? (
                  <p className="desk-rise flex items-center gap-3 text-sm text-[#6b645c]" aria-live="polite">
                    <span className="desk-wait" aria-hidden="true">
                      <i />
                      <i />
                      <i />
                    </span>
                    Reading the papers…
                  </p>
                ) : null}
              </div>
            )}
          </div>
        </div>
        <form
          className="relative px-6 pb-6"
          onSubmit={(event) => {
            event.preventDefault();
            if (showMenu) {
              pick(matches[cursor] ?? matches[0]);
              return;
            }
            void send();
          }}
        >
          <div className={`mx-auto w-full ${embedded ? "" : "max-w-2xl"}`}>
            {showMenu ? (
              <ul
                id="paper-mentions"
                role="listbox"
                className="desk-rise mb-2 overflow-hidden rounded-2xl bg-white ring-1 ring-[#e4dcd0]"
              >
                {matches.map((paper, index) => (
                  <li key={paper.job_id} className="flex items-stretch">
                    <button
                      type="button"
                      role="option"
                      aria-selected={index === cursor}
                      className={`flex min-w-0 flex-1 flex-col px-4 py-3 text-left ${index === cursor ? "bg-[#f4f0e6]" : "hover:bg-[#f4f0e6]"}`}
                      onMouseEnter={() => setCursor(index)}
                      onClick={() => pick(paper)}
                    >
                      <span className="text-sm">{nameOf(paper)}</span>
                      <span className="text-xs text-[#6b645c]">{paper.arxiv_id}</span>
                    </button>
                    <MorphLink
                      href={`/desk/${conferenceId}/${paper.job_id}`}
                      className="flex items-center px-4 text-xs text-[#6b645c]"
                    >
                      Open
                    </MorphLink>
                  </li>
                ))}
              </ul>
            ) : null}
            <div className="flex items-end gap-2 rounded-2xl bg-white px-4 py-3 ring-1 ring-[#e4dcd0]">
              <label className="sr-only" htmlFor="ask">
                Ask about these papers
              </label>
              <div
                role="combobox"
                aria-expanded={showMenu}
                aria-controls="paper-mentions"
                aria-haspopup="listbox"
                className="flex min-w-0 flex-1"
              >
                <textarea
                  id="ask"
                  ref={fieldRef}
                  value={draft}
                  rows={1}
                  placeholder="Ask about a paper. Type @ to name one."
                  aria-autocomplete="list"
                  onChange={(event) => {
                    setDraft(event.target.value);
                    setMenuOpen(true);
                    const field = event.target;
                    field.style.height = "auto";
                    field.style.height = `${Math.min(field.scrollHeight, 160)}px`;
                  }}
                  onKeyDown={(event) => {
                    if (showMenu && event.key === "ArrowDown") {
                      event.preventDefault();
                      setCursor((current) => (current + 1) % matches.length);
                      return;
                    }
                    if (showMenu && event.key === "ArrowUp") {
                      event.preventDefault();
                      setCursor((current) => (current - 1 + matches.length) % matches.length);
                      return;
                    }
                    if (event.key === "Escape") {
                      setMenuOpen(false);
                      if (panel) closePanel();
                      return;
                    }
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      if (showMenu) pick(matches[cursor] ?? matches[0]);
                      else void send();
                    }
                  }}
                  className="max-h-40 min-h-8 flex-1 resize-none bg-transparent py-1 text-sm outline-none"
                />
              </div>
              <button
                type="submit"
                disabled={busy}
                className="rounded-full bg-[#1c1915] px-4 py-2 text-xs text-[#f4f0e6] disabled:opacity-60"
              >
                {busy ? "…" : "Send"}
              </button>
            </div>
          </div>
        </form>
      </div>
      {onOpenQuote ? null : (
      <aside
        id="cited-passage"
        role="complementary"
        aria-label="Cited passage"
        className={`desk-panel shrink-0 overflow-hidden border-[#e4dcd0] ${
          passageOpen
            ? "h-[58vh] w-full border-t lg:h-auto lg:w-[min(36rem,42vw)] lg:border-t-0 lg:border-l"
            : "h-0 w-0 border-0"
        }`}
      >
        {panel?.kind === "quote" ? (
          <div className="flex h-full min-h-0 w-full flex-col lg:w-[min(36rem,42vw)]">
            <header className="flex items-start justify-between gap-3 border-b border-[#e4dcd0] bg-[#f4f0e6] px-4 py-3">
              <div>
                <p className="font-[family-name:var(--desk-serif)] text-lg leading-tight">{panel.quote.title}</p>
                <p className="mt-1 text-xs text-[#6b645c]">
                  {panel.quote.issue_type ? `${issueLabel(panel.quote.issue_type)} · ` : ""}
                  {panel.quote.page ? `Page ${panel.quote.page}` : "Paper"}
                </p>
                {panel.quote.reason ? (
                  <p className="mt-1 text-sm leading-6 text-[#1c1915]">{panel.quote.reason}</p>
                ) : null}
              </div>
              <div className="flex shrink-0 flex-col items-end gap-2">
                <MorphLink
                  href={`/desk/${conferenceId}/${panel.quote.job_id}`}
                  className="text-xs underline decoration-[#c4a15a] underline-offset-4"
                >
                  Full paper
                </MorphLink>
                <button type="button" className="text-xs underline decoration-[#c4a15a] underline-offset-4" onClick={closePanel}>
                  Close
                </button>
              </div>
            </header>
            {panel.quote.text && panel.quote.text !== panel.quote.reason ? (
              <p className="border-b border-[#e4dcd0] bg-[#f4f0e6] px-4 py-3 text-sm leading-6 text-[#1c1915]">
                {panel.quote.text}
              </p>
            ) : null}
            <div className="min-h-0 flex-1">
              <PdfView jobId={panel.quote.job_id} page={panel.quote.page} quote={panel.quote.text} />
            </div>
          </div>
        ) : null}
        {panel?.kind === "unread" ? (
          <div className="flex h-full min-h-0 w-full flex-col bg-[#f4f0e6] px-4 py-4 lg:w-[min(36rem,42vw)]">
            <header className="flex items-start justify-between gap-3">
              <p className="font-[family-name:var(--desk-serif)] text-lg leading-tight">{panel.title}</p>
              <button type="button" className="text-xs underline decoration-[#c4a15a] underline-offset-4" onClick={closePanel}>
                Close
              </button>
            </header>
            {panel.abstract ? (
              <details className="mt-4">
                <summary className="cursor-pointer text-xs text-[#1c1915] underline decoration-[#c4a15a] underline-offset-4">
                  Abstract
                </summary>
                <p className="mt-2 text-sm leading-6 text-[#1c1915]">{panel.abstract}</p>
              </details>
            ) : null}
            <p className="mt-4 text-sm leading-6 text-[#6b645c]">This paper has not been read yet.</p>
          </div>
        ) : null}
      </aside>
      )}
    </section>
  );
}

function Message({
  text,
  papers,
  conferenceId,
}: {
  text: string;
  papers: Paper[];
  conferenceId: string;
}) {
  const parts = text.split(/(@[^@\n]+)/g);
  return (
    <>
      {parts.map((part, index) => {
        if (!part.startsWith("@")) return <span key={index}>{part}</span>;
        const raw = part.slice(1).trim();
        const paper = papers.find(
          (item) => nameOf(item) === raw || item.arxiv_id === raw || raw.startsWith(nameOf(item)),
        );
        if (!paper) return <span key={index}>{part}</span>;
        return (
          <MorphLink
            key={index}
            href={`/desk/${conferenceId}/${paper.job_id}`}
            className="mx-0.5 inline-flex rounded-full bg-[#f4f0e6] px-2 py-0.5 text-[#1c1915]"
          >
            {nameOf(paper)}
          </MorphLink>
        );
      })}
    </>
  );
}
