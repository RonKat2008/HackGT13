"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import type { DeskVoiceAction } from "./voice-action";
import { queueChatPrompt } from "./voice-action";

type PaperRef = { job_id: string; title: string; arxiv_id: string };
type Engine = "grok" | "browser";

const RATES = new Set([8000, 16000, 22050, 24000, 32000, 44100, 48000]);
const MODEL = "grok-voice-think-fast-2.0";

const SHOW_SCREEN = {
  type: "function",
  name: "show_screen",
  description:
    "Change the desk screen, or send a question to the conference chat. Use view ask for errors, findings, or any question that should be answered in chat.",
  parameters: {
    type: "object",
    properties: {
      view: { type: "string", enum: ["summary", "chat", "paper", "ask"] },
      paper: { type: "string", description: "Title or arXiv id when view is paper." },
      ask: { type: "boolean", description: "Open the chatbot beside that paper." },
      prompt: { type: "string", description: "Question to send when view is ask." },
    },
    required: ["view"],
  },
};

function conferenceOf(path: string): string | null {
  const parts = path.split("/").filter(Boolean);
  if (parts[0] !== "desk" || !parts[1] || parts[1] === "login") return null;
  return parts[1];
}

function authorPath(path: string): boolean {
  return path === "/author" || path.startsWith("/author/");
}

function deskQuery(extra: Record<string, string>): string {
  const current = new URLSearchParams(window.location.search);
  const next = new URLSearchParams();
  if (current.get("example") === "1") next.set("example", "1");
  for (const [key, value] of Object.entries(extra)) next.set(key, value);
  const query = next.toString();
  return query ? `?${query}` : "";
}

function phraseFrom(args: { view?: string; paper?: string; ask?: boolean; prompt?: string }): string {
  const prompt = (args.prompt || "").trim();
  if (args.view === "ask") return prompt ? `ask the chat ${prompt}` : "pull up these errors";
  const paper = (args.paper || "").trim();
  if (args.view === "paper" && paper) {
    return args.ask ? `pull up ${paper} with chatbot` : `pull up ${paper}`;
  }
  if (args.view === "chat") return "pull up chat";
  return "pull up summary";
}

function looksLikeNav(text: string): boolean {
  return /\b(pull up|bring up|show me|switch to|go to|open|show|summary|chat|errors?|issues|findings|ask)\b/i.test(text);
}

function encodeBase64(bytes: Uint8Array): string {
  let binary = "";
  const size = 0x8000;
  for (let index = 0; index < bytes.length; index += size) {
    binary += String.fromCharCode(...bytes.subarray(index, index + size));
  }
  return btoa(binary);
}

function floatToPcm16(input: Float32Array): Uint8Array {
  const pcm = new Int16Array(input.length);
  for (let index = 0; index < input.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, input[index]));
    pcm[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return new Uint8Array(pcm.buffer);
}

function instructionsFor(papers: PaperRef[], author: boolean): string {
  const names = papers.slice(0, 30).map((paper) => {
    const title = (paper.title || paper.arxiv_id).slice(0, 80);
    return `${title} (${paper.arxiv_id})`;
  });
  return [
    "You are the silent control for the PreSearch desk. Do not speak.",
    author
      ? "When the author asks to pull up, show, or open a screen, call show_screen and say nothing."
      : "When the chair asks to pull up, show, or open a screen, call show_screen and say nothing.",
    author
      ? "view summary stays on this paper. view chat stays on this paper's chat."
      : "view summary opens the summary. view chat opens the conference chat.",
    "view paper opens a paper. Put the title or arXiv id in paper. Set ask true when they want the chatbot with that paper.",
    author
      ? "view ask sends a question into this paper's chat. Use it for errors, findings, issues, or any question about the paper. Put their request in prompt."
      : "view ask sends a question into the conference chat. Use it for errors, findings, issues, or any question about the papers. Put their request in prompt.",
    "Never change a stored verdict.",
    names.length ? `Papers: ${names.join("; ")}.` : "No papers are on the list yet.",
  ].join(" ");
}

type SpeechRec = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

function browserRecognition(): SpeechRec | null {
  const host = window as Window & {
    SpeechRecognition?: new () => SpeechRec;
    webkitSpeechRecognition?: new () => SpeechRec;
  };
  const Ctor = host.SpeechRecognition || host.webkitSpeechRecognition;
  return Ctor ? new Ctor() : null;
}

export function VoiceDesk() {
  const path = usePathname();
  const router = useRouter();
  const conferenceId = conferenceOf(path);
  const onAuthor = authorPath(path);
  const [listening, setListening] = useState(false);
  const [engine, setEngine] = useState("");
  const [heard, setHeard] = useState("");
  const [error, setError] = useState("");
  const papersRef = useRef<PaperRef[]>([]);
  const conferenceRef = useRef(conferenceId);
  const authorRef = useRef(onAuthor);
  const recent = useRef({ key: "", at: 0 });
  const live = useRef(false);
  const listeningRef = useRef(false);
  const stopRef = useRef<(() => void) | null>(null);
  const toggleRef = useRef<() => void>(() => {});
  const routerRef = useRef(router);
  listeningRef.current = listening;
  conferenceRef.current = conferenceId;
  authorRef.current = onAuthor;
  routerRef.current = router;

  useEffect(() => {
    if (!conferenceId && !onAuthor) return;
    let cancelled = false;
    const url = onAuthor ? "/api/author/papers" : `/api/desk/conferences/${conferenceId}`;
    void fetch(url).then(async (response) => {
      if (!response.ok || cancelled) return;
      const body = (await response.json()) as { papers?: PaperRef[] };
      if (!Array.isArray(body.papers)) return;
      papersRef.current = body.papers.map((paper) => ({
        job_id: paper.job_id,
        title: paper.title || "",
        arxiv_id: paper.arxiv_id || "",
      }));
    });
    return () => {
      cancelled = true;
    };
  }, [conferenceId, onAuthor]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.repeat || event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key?.toLowerCase() !== "v") return;
      const target = event.target;
      if (target instanceof HTMLElement) {
        const tag = target.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA" || target.isContentEditable) return;
      }
      event.preventDefault();
      toggleRef.current();
    }
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      stopRef.current?.();
    };
  }, []);

  useEffect(() => {
    live.current = false;
    stopRef.current?.();
    stopRef.current = null;
    setListening(false);
    setEngine("");
  }, [conferenceId]);

  async function command(text: string): Promise<DeskVoiceAction | null> {
    const response = await fetch("/api/desk/voice/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, papers: papersRef.current }),
    });
    if (!response.ok) return null;
    const body = (await response.json()) as { action?: DeskVoiceAction | null };
    return body.action ?? null;
  }

  function apply(action: DeskVoiceAction | null, _via: Engine) {
    if (!action) return;
    if (action.type === "refuse" || action.type === "clarify") {
      setHeard(action.say || "");
      return;
    }
    const key = `${action.type}:${action.view || ""}:${action.job_id || ""}:${action.ask ? 1 : 0}:${action.text || ""}`;
    const now = Date.now();
    if (recent.current.key === key && now - recent.current.at < 3000) return;
    recent.current = { key, at: now };
    const id = conferenceRef.current;
    const author = authorRef.current;
    if (!id && !author) return;
    if (action.type === "prompt" && action.text) queueChatPrompt(action.text);
    window.dispatchEvent(new CustomEvent("desk-voice", { detail: action }));
    if (author) {
      if (action.type === "prompt") setHeard("Sent to chat");
      else if (action.type === "open") setHeard("Opening the paper");
      else if (action.type === "show") setHeard(action.view === "chat" ? "Chat." : "On this paper.");
      return;
    }
    if (action.type === "prompt") {
      setHeard("Sent to chat");
      routerRef.current.push(`/desk/${id}${deskQuery({ view: "chat" })}`);
      return;
    }
    if (action.type === "show" && action.view) {
      routerRef.current.push(`/desk/${id}${deskQuery({ view: action.view })}`);
      return;
    }
    if (action.type === "open" && action.job_id) {
      routerRef.current.push(`/desk/${id}/${action.job_id}${deskQuery(action.ask ? { ask: "1" } : {})}`);
    }
  }

  function stop() {
    live.current = false;
    stopRef.current?.();
    stopRef.current = null;
    setListening(false);
    setEngine("");
  }

  async function startBrowser(mine: { current: boolean }) {
    const recognition = browserRecognition();
    if (!recognition) {
      live.current = false;
      setError("Voice needs a microphone.");
      setListening(false);
      return;
    }
    setEngine("Browser voice");
    setError("");
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = "en-US";
    recognition.onresult = (event) => {
      const result = event.results[event.results.length - 1];
      const text = result?.[0]?.transcript || "";
      if (!text) return;
      setHeard(text);
      void command(text).then((action) => {
        if (mine.current) apply(action, "browser");
      });
    };
    recognition.onerror = () => {
      if (mine.current) setError("Voice needs a microphone.");
    };
    recognition.onend = () => {
      if (!mine.current) return;
      try {
        recognition.start();
      } catch {
        setListening(false);
      }
    };
    stopRef.current = () => {
      mine.current = false;
      recognition.onend = null;
      recognition.stop();
    };
    recognition.start();
    setListening(true);
  }

  async function start() {
    if (live.current) return;
    live.current = true;
    setListening(true);
    setError("");
    setHeard("");
    const mine = { current: true };
    stopRef.current = () => {
      mine.current = false;
    };
    let token = "";
    try {
      const response = await fetch("/api/desk/voice/token", { method: "POST" });
      if (response.ok) {
        const body = (await response.json()) as { value?: string };
        token = body.value || "";
      }
    } catch {
      token = "";
    }
    if (!mine.current) return;
    if (!token) {
      await startBrowser(mine);
      return;
    }

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      await startBrowser(mine);
      return;
    }
    if (!mine.current) {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }

    const audio = new AudioContext();
    await audio.resume();
    const rate = RATES.has(audio.sampleRate) ? audio.sampleRate : 24000;
    const ws = new WebSocket(`wss://api.x.ai/v1/realtime?model=${MODEL}`, [`xai-client-secret.${token}`]);
    const source = audio.createMediaStreamSource(stream);
    const processor = audio.createScriptProcessor(4096, 1, 1);
    const mute = audio.createGain();
    mute.gain.value = 0;
    let toolAt = 0;
    let transcriptTimer = 0;
    let fellBack = false;
    const pending: string[] = [];
    let ready = false;

    function release() {
      window.clearTimeout(transcriptTimer);
      processor.onaudioprocess = null;
      processor.disconnect();
      source.disconnect();
      stream.getTracks().forEach((track) => track.stop());
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) ws.close();
      void audio.close();
    }

    processor.onaudioprocess = (event) => {
      if (!mine.current) return;
      const input = event.inputBuffer.getChannelData(0);
      const payload = JSON.stringify({
        type: "input_audio_buffer.append",
        audio: encodeBase64(floatToPcm16(input)),
      });
      if (ws.readyState === WebSocket.OPEN && ready) ws.send(payload);
      else {
        pending.push(payload);
        if (pending.length > 24) pending.shift();
      }
    };
    source.connect(processor);
    processor.connect(mute);
    mute.connect(audio.destination);

    ws.onopen = () => {
      if (!mine.current) return;
      const titles = papersRef.current.map((paper) => (paper.title || paper.arxiv_id).slice(0, 50)).slice(0, 20);
      ws.send(
        JSON.stringify({
          type: "session.update",
          session: {
            voice: "eve",
            instructions: instructionsFor(papersRef.current, authorRef.current),
            turn_detection: { type: "server_vad" },
            tools: [SHOW_SCREEN],
            audio: {
              input: {
                format: { type: "audio/pcm", rate },
                transcription: {
                  model: "grok-transcribe",
                  language_hint: "en",
                  keyterms: ["PreSearch", "arXiv", ...titles],
                },
              },
              output: { format: { type: "audio/pcm", rate } },
            },
          },
        }),
      );
      ready = true;
      for (const chunk of pending) ws.send(chunk);
      pending.length = 0;
      setEngine("Grok voice");
      setListening(true);
    };

    ws.onmessage = (message) => {
      if (typeof message.data !== "string") return;
      type VoiceEvent = {
        type?: string;
        delta?: string;
        name?: string;
        call_id?: string;
        arguments?: string;
        transcript?: string;
        error?: { message?: string };
      };
      let event: VoiceEvent;
      try {
        event = JSON.parse(message.data) as VoiceEvent;
      } catch {
        return;
      }
      if (event.type === "response.output_audio.delta" || event.type === "response.audio.delta") return;
      if (event.type === "input_audio_buffer.speech_started") {
        window.clearTimeout(transcriptTimer);
        return;
      }
      if (event.type === "response.function_call_arguments.done" && event.name === "show_screen") {
        toolAt = Date.now();
        let args: { view?: string; paper?: string; ask?: boolean; prompt?: string } = {};
        try {
          args = JSON.parse(event.arguments || "{}") as {
            view?: string;
            paper?: string;
            ask?: boolean;
            prompt?: string;
          };
        } catch {
          args = {};
        }
        void command(phraseFrom(args)).then((action) => {
          if (!mine.current) return;
          apply(action, "grok");
          if (ws.readyState !== WebSocket.OPEN) return;
          ws.send(
            JSON.stringify({
              type: "conversation.item.create",
              item: {
                type: "function_call_output",
                call_id: event.call_id,
                output: JSON.stringify({ ok: Boolean(action) }),
              },
            }),
          );
        });
        return;
      }
      const transcript =
        event.type === "conversation.item.input_audio_transcription.updated" ||
        event.type === "conversation.item.input_audio_transcription.completed"
          ? event.transcript || ""
          : "";
      if (transcript && looksLikeNav(transcript)) {
        setHeard(transcript);
        window.clearTimeout(transcriptTimer);
        transcriptTimer = window.setTimeout(() => {
          if (!mine.current || Date.now() - toolAt < 1200) return;
          void command(transcript).then((action) => {
            if (mine.current) apply(action, "grok");
          });
        }, 700);
      }
      if (event.type === "error" && event.error?.message) setError("Grok voice dropped. Try again.");
    };

    ws.onerror = () => {
      if (!mine.current || fellBack) return;
      fellBack = true;
      release();
      void startBrowser(mine);
    };

    stopRef.current = () => {
      mine.current = false;
      release();
      setListening(false);
    };
  }

  toggleRef.current = () => {
    if (!conferenceRef.current && !authorRef.current) return;
    if (listeningRef.current) stop();
    else void start();
  };

  if (!conferenceId && !onAuthor) return null;

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-30 flex flex-col items-end gap-2">
      {error || heard ? (
        <p className="pointer-events-none max-w-56 rounded-2xl bg-[#1c1915] px-3 py-2 text-xs text-[#f4f0e6] shadow-lg">
          {error || heard}
        </p>
      ) : null}
      <button
        type="button"
        aria-pressed={listening}
        aria-keyshortcuts="v"
        title={listening ? `${engine}. Press V to stop.` : "Press V for voice"}
        onClick={() => void (listening ? stop() : start())}
        className="pointer-events-auto rounded-full bg-[#c4a15a] px-3 py-2 text-xs text-[#1c1915] shadow-lg"
      >
        {listening ? "Listening" : "Voice"}
        <span className="ml-2 rounded bg-[#1c1915]/10 px-1">V</span>
      </button>
    </div>
  );
}
