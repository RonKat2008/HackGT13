"use client";

import { useEffect, useState } from "react";

type AddState = { error: string; added: number };

function AddButton({ empty, busy }: { empty: boolean; busy: boolean }) {
  return (
    <button
      className="w-fit rounded-full bg-[#1c1915] px-3 py-1.5 text-xs text-[#f4f0e6] disabled:opacity-40"
      disabled={busy || empty}
      type="submit"
    >
      {busy ? "Adding" : "Add papers"}
    </button>
  );
}

export function AddPapersForm({
  action,
}: {
  action: (state: AddState, formData: FormData) => Promise<AddState>;
}) {
  const [lines, setLines] = useState("");
  const [state, setState] = useState<AddState>({ error: "", added: 0 });
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (state.added > 0) setLines("");
  }, [state]);

  return (
    <form
      action={async (formData) => {
        setPending(true);
        try {
          const next = await action(state, formData);
          setState(next);
        } finally {
          setPending(false);
        }
      }}
      className="relative z-10 flex shrink-0 flex-col gap-2 text-xs"
    >
      <label className="sr-only" htmlFor="paper-lines">
        Add arXiv ids
      </label>
      <textarea
        id="paper-lines"
        name="lines"
        rows={3}
        value={lines}
        onChange={(event) => setLines(event.target.value)}
        className="bg-white/70 px-3 py-2 text-xs outline-none"
        placeholder={"1706.03762\n1810.04805"}
      />
      {state.error ? (
        <p className="text-[#8c3a2f]" role="alert">
          {state.error}
        </p>
      ) : null}
      <AddButton busy={pending} empty={lines.trim() === ""} />
    </form>
  );
}
