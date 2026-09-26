"use client";

import { FormEvent, useState } from "react";

export type ConferenceIssue = {
  issue_type: "citation" | "number" | "dataset" | "test" | "support";
  claim_text: string;
  evidence_span: string;
  jev_label: string;
  reason: string;
};

export type ConferencePaper = {
  paper_id: string;
  title: string;
  arxiv_id: string;
  author_name: string;
  author_email: string | null;
  contacted_at: string | null;
  status: string;
  issues: ConferenceIssue[];
};

export type Conference = {
  conference_id: string;
  name: string;
  contact_email: string;
};

export type ConferenceProbe = {
  auc: number;
  hidden: boolean;
};

type PaperState = {
  author_email: string | null;
  contacted_at: string | null;
  draftEmail: string;
};

function buildMailtoHref(paper: ConferencePaper, authorEmail: string): string {
  const bodyLines: string[] = [];
  for (const issue of paper.issues) {
    bodyLines.push(issue.reason);
    bodyLines.push(issue.evidence_span);
  }
  bodyLines.push(`https://arxiv.org/abs/${paper.arxiv_id}`);
  const body = bodyLines.join("\n\n");
  return `mailto:${authorEmail}?subject=${encodeURIComponent(paper.title)}&body=${encodeURIComponent(body)}`;
}

export function ConferenceDashboard({
  conference,
  papers,
  probe,
}: {
  conference: Conference;
  papers: ConferencePaper[];
  probe: ConferenceProbe;
}) {
  const [paperState, setPaperState] = useState<Record<string, PaperState>>(
    () =>
      Object.fromEntries(
        papers.map((paper) => [
          paper.paper_id,
          {
            author_email: paper.author_email,
            contacted_at: paper.contacted_at,
            draftEmail: "",
          },
        ]),
      ),
  );

  function saveEmail(paperId: string, event: FormEvent) {
    event.preventDefault();
    const draft = paperState[paperId]?.draftEmail.trim() ?? "";
    if (!draft) return;
    setPaperState((prev) => ({
      ...prev,
      [paperId]: {
        ...prev[paperId],
        author_email: draft,
        draftEmail: "",
      },
    }));
  }

  function markContacted(paperId: string) {
    const contactedAt = new Date().toISOString();
    setPaperState((prev) => ({
      ...prev,
      [paperId]: {
        ...prev[paperId],
        contacted_at: contactedAt,
      },
    }));
  }

  return (
    <div className="flex flex-col gap-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">
          {conference.name}
        </h1>
        <p className="mt-1 text-sm text-zinc-600">
          Conference dashboard · {conference.contact_email}
        </p>
        {!probe.hidden ? (
          <p className="mt-2 text-sm text-zinc-500">
            AI-likeness may sort this list. It is not a reason to email.
          </p>
        ) : null}
      </header>

      <ul className="flex flex-col gap-6">
        {papers.map((paper) => {
          const state = paperState[paper.paper_id];
          const authorEmail = state?.author_email ?? null;
          const contactedAt = state?.contacted_at ?? null;

          return (
            <li
              key={paper.paper_id}
              className="border-b border-zinc-200 pb-6 last:border-b-0"
            >
              <div className="flex flex-col gap-3">
                <div>
                  <h2 className="text-lg font-medium text-zinc-900">
                    {paper.title}
                  </h2>
                  <p className="mt-1 text-sm text-zinc-600">
                    arXiv:{paper.arxiv_id} · {paper.author_name} ·{" "}
                    {authorEmail ?? "No email"} · {paper.status}
                  </p>
                </div>

                <ul className="flex flex-col gap-1 text-sm text-zinc-800">
                  {paper.issues.map((issue, index) => (
                    <li key={`${paper.paper_id}-issue-${index}`}>
                      {issue.reason}
                    </li>
                  ))}
                </ul>

                <div className="flex flex-col gap-2 text-sm">
                  {authorEmail ? (
                    <>
                      <a
                        href={buildMailtoHref(paper, authorEmail)}
                        className="w-fit text-zinc-900 underline underline-offset-2"
                        onClick={() => markContacted(paper.paper_id)}
                      >
                        Email about these issues.
                      </a>
                      {contactedAt ? (
                        <p className="text-zinc-600">
                          Draft started · {contactedAt}
                        </p>
                      ) : null}
                    </>
                  ) : (
                    <form
                      className="flex flex-wrap items-end gap-2"
                      onSubmit={(event) => saveEmail(paper.paper_id, event)}
                    >
                      <label className="flex flex-col gap-1">
                        <span className="text-zinc-700">Add author email</span>
                        <input
                          type="email"
                          value={state?.draftEmail ?? ""}
                          onChange={(event) =>
                            setPaperState((prev) => ({
                              ...prev,
                              [paper.paper_id]: {
                                ...prev[paper.paper_id],
                                draftEmail: event.target.value,
                              },
                            }))
                          }
                          className="border border-zinc-300 px-2 py-1 text-zinc-900"
                          placeholder="author@example.edu"
                          required
                        />
                      </label>
                      <button
                        type="submit"
                        className="border border-zinc-900 bg-zinc-900 px-3 py-1 text-white"
                      >
                        Save
                      </button>
                    </form>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
