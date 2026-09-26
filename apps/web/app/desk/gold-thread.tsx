"use client";

import { useEffect, useState } from "react";

export function GoldThread({ from }: { from: HTMLElement | null }) {
  const [path, setPath] = useState("");

  useEffect(() => {
    if (!from) {
      setPath("");
      return;
    }
    function measure() {
      if (!from?.isConnected) {
        setPath("");
        return;
      }
      const band = [...document.querySelectorAll(".pdf-band")].find((node) => {
        const rect = node.getBoundingClientRect();
        return rect.width > 2 && rect.height > 2;
      });
      const panel = document.getElementById("cited-passage");
      const target = band ?? panel;
      if (!target) {
        setPath("");
        return;
      }
      const start = from.getBoundingClientRect();
      const end = target.getBoundingClientRect();
      if (end.width < 2 || end.height < 2) {
        setPath("");
        return;
      }
      const x1 = start.left + start.width / 2;
      const y1 = start.top + start.height / 2;
      const x2 = end.left + Math.min(28, end.width / 2);
      const y2 = end.top + end.height / 2;
      const bend = Math.max(40, Math.abs(x2 - x1) / 2);
      setPath(`M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`);
    }
    measure();
    const timer = window.setInterval(measure, 240);
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [from]);

  if (!path) return null;
  return (
    <svg className="pointer-events-none fixed inset-0 z-40 h-dvh w-dvw" aria-hidden="true">
      <path d={path} fill="none" stroke="#c4a15a" strokeWidth="1.5" />
    </svg>
  );
}
