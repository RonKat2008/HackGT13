export type DeskVoiceAction = {
  type: "show" | "open" | "refuse" | "clarify" | "prompt";
  view?: "summary" | "chat";
  job_id?: string;
  title?: string;
  ask?: boolean;
  say?: string;
  text?: string;
};

let pendingPrompt: string | null = null;

export function queueChatPrompt(text: string) {
  pendingPrompt = text;
}

export function takeChatPrompt(): string | null {
  const text = pendingPrompt;
  pendingPrompt = null;
  return text;
}
