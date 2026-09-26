"use client";

import { createElement, Fragment, useEffect, useState } from "react";
import type { Run } from "@/lib/api";
import { Claims } from "./claims";
import { RoundDiff } from "./diff";

function hasFinalStatus(run: Run): boolean {
  return Boolean(run.final_status);
}

export function RunPoll({
  id,
  initialRun,
  initialError,
  fetchRun,
}: {
  id: string;
  initialRun: Run | null;
  initialError: string | null;
  fetchRun: (id: string) => Promise<Run>;
}) {
  const [run, setRun] = useState<Run | null>(initialRun);
  const [error, setError] = useState<string | null>(initialError);

  useEffect(() => {
    if (!id) return;
    if (initialRun && hasFinalStatus(initialRun)) return;

    let stopped = false;
    const startedAt = Date.now();

    const intervalId = setInterval(() => {
      void (async () => {
        if (stopped) return;
        if (Date.now() - startedAt >= 60_000) {
          stopped = true;
          clearInterval(intervalId);
          return;
        }
        try {
          const next = await fetchRun(id);
          if (stopped) return;
          setRun(next);
          setError(null);
          if (hasFinalStatus(next)) {
            stopped = true;
            clearInterval(intervalId);
          }
        } catch (err) {
          if (stopped) return;
          setError(
            err instanceof Error ? err.message : "Failed to load run.",
          );
          if (Date.now() - startedAt >= 60_000) {
            stopped = true;
            clearInterval(intervalId);
          }
        }
      })();
    }, 1000);

    return () => {
      stopped = true;
      clearInterval(intervalId);
    };
  }, [id, fetchRun, initialRun]);

  const errorAlert = error
    ? createElement(
        "p",
        {
          role: "alert",
          className:
            "mb-8 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800",
        },
        error,
      )
    : null;

  const summary = run
    ? createElement(
        Fragment,
        null,
        createElement(
          "dl",
          { className: "flex flex-col gap-4 text-sm" },
          createElement(
            "div",
            null,
            createElement(
              "dt",
              { className: "font-medium text-zinc-700" },
              "Goal",
            ),
            createElement(
              "dd",
              { className: "mt-1 text-zinc-900" },
              run.goal,
            ),
          ),
          createElement(
            "div",
            null,
            createElement(
              "dt",
              { className: "font-medium text-zinc-700" },
              "Product",
            ),
            createElement(
              "dd",
              { className: "mt-1 text-zinc-900" },
              run.product,
            ),
          ),
          createElement(
            "div",
            null,
            createElement(
              "dt",
              { className: "font-medium text-zinc-700" },
              "Final status",
            ),
            createElement(
              "dd",
              { className: "mt-1 text-zinc-900" },
              run.final_status,
            ),
          ),
          createElement(
            "div",
            null,
            createElement(
              "dt",
              { className: "font-medium text-zinc-700" },
              "Fitness",
            ),
            createElement(
              "dd",
              { className: "mt-1 text-zinc-900" },
              run.fitness,
            ),
          ),
          typeof run.replay_of === "string"
            ? createElement(
                "div",
                null,
                createElement(
                  "dt",
                  { className: "font-medium text-zinc-700" },
                  "Replay of",
                ),
                createElement(
                  "dd",
                  { className: "mt-1 text-zinc-900" },
                  run.replay_of,
                ),
              )
            : null,
        ),
        createElement(Claims, { run }),
        createElement(RoundDiff, { run }),
      )
    : null;

  return createElement(Fragment, null, errorAlert, summary);
}
