"use client";

import { useEffect, useRef, useState } from "react";

export function ReportVoice({ jobId, claim }: { jobId: string; claim: string }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef<string | null>(null);
  const token = useRef(0);
  const [state, setState] = useState<"idle" | "loading" | "playing">("idle");
  const [voice, setVoice] = useState("");
  const [error, setError] = useState("");
  const [why, setWhy] = useState("");

  useEffect(() => {
    return () => {
      audioRef.current?.pause();
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
      window.speechSynthesis?.cancel();
    };
  }, []);

  function stopPlayback() {
    audioRef.current?.pause();
    audioRef.current = null;
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
    }
    window.speechSynthesis?.cancel();
  }

  function stop() {
    token.current += 1;
    stopPlayback();
    setState("idle");
  }

  async function speak(question = "") {
    const mine = token.current + 1;
    token.current = mine;
    stopPlayback();
    setState("loading");
    setError("");
    setVoice("");
    try {
      const response = await fetch(`/api/desk/papers/${jobId}/speak`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, claim }),
      });
      const body = (await response.json()) as { script?: string; audio?: string | null; voice?: string };
      if (token.current !== mine) return;
      if (!response.ok || !body.script) {
        setError("Voice is unavailable.");
        setState("idle");
        return;
      }
      if (body.audio) {
        const binary = atob(body.audio);
        const bytes = new Uint8Array(binary.length);
        for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
        const objectUrl = URL.createObjectURL(new Blob([bytes], { type: "audio/mpeg" }));
        urlRef.current = objectUrl;
        const player = new Audio(objectUrl);
        audioRef.current = player;
        player.onended = () => {
          if (token.current === mine) setState("idle");
        };
        try {
          await player.play();
          if (token.current === mine) {
            setVoice("Grok voice");
            setState("playing");
          }
          return;
        } catch {
          stopPlayback();
        }
      }
      const utter = new SpeechSynthesisUtterance(body.script);
      utter.onend = () => {
        if (token.current === mine) setState("idle");
      };
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utter);
      setVoice("Browser voice");
      setState("playing");
    } catch {
      if (token.current !== mine) return;
      setError("Voice is unavailable.");
      setState("idle");
    }
  }

  return (
    <div className="mt-4">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => void speak()}
          disabled={state === "loading"}
          className="rounded-full bg-[#1c1915] px-3 py-1.5 text-xs text-[#f4f0e6] disabled:opacity-60"
        >
          {state === "playing" ? "Speaking" : "Listen"}
        </button>
        <button
          type="button"
          onClick={stop}
          disabled={state === "idle"}
          className="rounded-full bg-white px-3 py-1.5 text-xs text-[#1c1915] ring-1 ring-[#e4dcd0] disabled:opacity-60"
        >
          Stop
        </button>
        {voice ? <span className="text-xs text-[#6b645c]">{voice}</span> : null}
      </div>
      <form
        className="mt-3 flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void speak(why.trim() || "Why is this one here?");
        }}
      >
        <input
          value={why}
          onChange={(event) => setWhy(event.target.value)}
          placeholder="Why is this one here?"
          aria-label="Ask why this row is here"
          className="min-w-0 flex-1 rounded-full bg-white px-3 py-1.5 text-xs outline-none ring-1 ring-[#e4dcd0]"
        />
        <button type="submit" className="rounded-full bg-white px-3 py-1.5 text-xs text-[#1c1915] ring-1 ring-[#e4dcd0]">
          Ask
        </button>
      </form>
      {error ? <p className="mt-2 text-xs text-[#8c3a2f]">{error}</p> : null}
    </div>
  );
}
