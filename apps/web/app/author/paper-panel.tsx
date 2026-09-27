"use client";

import { useState, type FormEvent } from "react";

export type FixturePaper = {
  title: string;
  arxiv_id: string;
  status: string;
  finding_count: number;
  issue_reason: string;
};

export function PaperPanel({ paper }: { paper: FixturePaper }) {
  const [shown, setShown] = useState(false);

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const arxiv = String(data.get("arxiv_id") ?? "").trim();
    const file = data.get("pdf");
    const hasFile = file instanceof File && file.size > 0;
    if (!arxiv && !hasFile) return;
    setShown(true);
  }

  if (shown) {
    return (
      <article className="max-w-xl border-l-2 border-[#c4a15a] pl-5">
        <p className="text-[11px] tracking-[0.16em] text-[#6b645c]">{paper.arxiv_id}</p>
        <h1 className="mt-2 font-[family-name:var(--desk-serif)] text-3xl leading-tight text-[#1c1915]">
          {paper.title}
        </h1>
        <div className="mt-4 flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm">
          <span className="text-[#8c3a2f]">{paper.status}</span>
          <span className="text-[#6b645c]">
            {paper.finding_count} {paper.finding_count === 1 ? "finding" : "findings"}
          </span>
        </div>
        <p className="mt-3 text-sm leading-6 text-[#6b645c]">{paper.issue_reason}</p>
      </article>
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex max-w-md flex-col gap-5">
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
      <button
        type="submit"
        className="w-fit rounded-full bg-[#1c1915] px-5 py-3 text-sm text-[#f4f0e6]"
      >
        Open the paper
      </button>
    </form>
  );
}
