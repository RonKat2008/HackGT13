"use client";

import { useRef, useState } from "react";

const STAGES = [
  { id: "parse", title: "Parse", text: "The PDF becomes text, section by section." },
  { id: "claims", title: "Claims", text: "Sentences that cite, count, or say “we show” are pulled out." },
  { id: "evidence", title: "Evidence", text: "The sentences beside a claim stay attached to it." },
  { id: "citations", title: "Citations", text: "Each citation is matched to the bibliography, then the catalogs." },
  { id: "numbers", title: "Numbers", text: "An abstract number is checked against the rest of the paper." },
  { id: "tables", title: "Tables", text: "A claimed gain is scored against the nearest table with an Ours row." },
  { id: "stamp", title: "Stamp", text: "The report keeps the sentence, the passage, and the reason." },
] as const;

const QUESTIONS = [
  {
    title: "What did the paper claim?",
    tag: "The sentence",
    slip: "Accuracy reached 95.2% on the public benchmark.",
  },
  {
    title: "What did ArxAudit investigate?",
    tag: "The check",
    slip: "A citation, a number, a table, or the paper’s own statement.",
  },
  {
    title: "What evidence did it find?",
    tag: "The passage",
    slip: "The sentence beside it, and the table cell when one exists.",
  },
  {
    title: "Why should the reviewer care?",
    tag: "The reason",
    slip: "The number 95.2 in the abstract is absent from the results.",
  },
] as const;

const ROW = 18;
const RADIUS = 2.4;

function bump(distance: number) {
  if (distance >= RADIUS) return 0;
  return 0.5 * (1 + Math.cos(Math.PI * (distance / RADIUS)));
}

export function StageWalk() {
  const listRef = useRef<HTMLDivElement>(null);
  const [pointer, setPointer] = useState(0);
  const [strength, setStrength] = useState(1);
  const [active, setActive] = useState(0);
  const [open, setOpen] = useState(true);
  const last = STAGES.length - 1;
  const stage = STAGES[active];
  const cardTop = Math.min(Math.max((pointer + 0.5) * ROW - 52, 0), STAGES.length * ROW - 104);

  function engage(row: number) {
    const clamped = Math.min(Math.max(row, 0), last);
    setPointer(clamped);
    setActive(Math.round(clamped));
    setStrength(1);
    setOpen(true);
  }

  return (
    <div className="grid items-center gap-12 lg:grid-cols-[minmax(0,1fr)_auto]">
      <div className="max-w-xl">
        <p className="text-[11px] tracking-[0.18em] text-[#8c3a2f]">THE WALK</p>
        <h2 className="mt-3 font-[family-name:var(--desk-serif)] text-4xl leading-tight">
          Move down the rail. Each tick is one pass.
        </h2>
        <p className="mt-4 max-w-md text-sm leading-6 text-[#6b645c]">
          The desk reads a paper in order. The card beside the rail is the pass under your hand.
        </p>
      </div>
      <div className="relative min-h-64 py-6 lg:pr-72">
        <div
          ref={listRef}
          role="listbox"
          aria-label="Passes in a read"
          aria-activedescendant={open ? `stage-${stage.id}` : undefined}
          className="flex w-16 flex-col"
          onPointerMove={(event) => {
            const rect = listRef.current?.getBoundingClientRect();
            if (!rect) return;
            engage((event.clientY - rect.top) / ROW - 0.5);
          }}
          onPointerLeave={() => {
            setPointer(active);
            setStrength(1);
            setOpen(true);
          }}
        >
          {STAGES.map((item, index) => {
            const rise = strength * bump(Math.abs(index - pointer));
            return (
              <button
                key={item.id}
                id={`stage-${item.id}`}
                type="button"
                role="option"
                aria-selected={open && index === active}
                className="flex h-[18px] items-center outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#c4a15a]"
                onFocus={() => engage(index)}
              >
                <span
                  className="stage-tick block h-[2px] rounded-full"
                  style={{
                    width: 14 + rise * 50,
                    opacity: 0.28 + rise * 0.72,
                    background: rise > 0.45 ? "#c4a15a" : "#1c1915",
                  }}
                />
              </button>
            );
          })}
        </div>
        <p className="mt-4 max-w-sm text-sm leading-6 text-[#6b645c] lg:hidden">
          <span className="font-[family-name:var(--desk-serif)] text-[#1c1915]">{stage.title}. </span>
          {stage.text}
        </p>
        <div
          aria-hidden={!open}
          className="reading-slip pointer-events-none absolute left-20 z-10 hidden w-64 rounded-2xl bg-white px-4 py-3 shadow-[0_16px_36px_-18px_rgba(28,25,21,0.45)] ring-1 ring-[#e4dcd0] lg:block"
          style={{ top: cardTop, opacity: open ? 1 : 0 }}
        >
          <p className="text-[11px] tracking-[0.14em] text-[#8a6a2f]">
            {String(active + 1).padStart(2, "0")}
          </p>
          <p className="mt-1 font-[family-name:var(--desk-serif)] text-xl leading-tight">{stage.title}</p>
          <p className="mt-2 text-sm leading-6 text-[#6b645c]">{stage.text}</p>
        </div>
      </div>
    </div>
  );
}

export function FindingIndex() {
  const [hover, setHover] = useState<number | null>(null);
  const row = hover === null ? QUESTIONS[0] : QUESTIONS[hover];

  return (
    <div className="grid items-start gap-10 lg:grid-cols-[minmax(0,36rem)_16rem]">
      <div>
        {QUESTIONS.map((item, index) => {
          const on = hover === null || hover === index;
          return (
            <div
              key={item.title}
              className="group flex items-baseline gap-4 border-t border-[#e4dcd0] py-4 last:border-b"
              onPointerEnter={() => setHover(index)}
              onPointerLeave={() => setHover(null)}
            >
              <p
                className={`font-[family-name:var(--desk-serif)] text-xl transition-colors duration-200 ${
                  on ? "text-[#1c1915]" : "text-[#1c1915]/30"
                }`}
              >
                {item.title}
              </p>
              <p className="min-w-0 flex-1 truncate text-xs text-[#6b645c]">{item.tag}</p>
              <p className="text-[11px] tabular-nums text-[#6b645c]">0{index + 1}</p>
              <span
                aria-hidden="true"
                className="text-[#1c1915]/40 transition-transform duration-300 group-hover:translate-x-1 group-hover:text-[#1c1915]"
              >
                →
              </span>
            </div>
          );
        })}
      </div>
      <aside className="reading-slip hidden rounded-xl bg-[#f7f3ea] p-4 ring-1 ring-[#e4dcd0] lg:block">
        <p className="text-[11px] tracking-[0.14em] text-[#8a6a2f]">{row.tag}</p>
        <p className="mt-2 border-l border-[#c4a15a] pl-3 font-[family-name:var(--desk-serif)] text-lg leading-snug">
          {row.slip}
        </p>
      </aside>
    </div>
  );
}
