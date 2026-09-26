"use client";

import { usePathname } from "next/navigation";

export function DeskChrome({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const login = path === "/desk/login";

  return (
    <div
      className={`flex min-h-0 flex-1 flex-col bg-[#f4f0e6] text-[#1c1915] ${login ? "overflow-auto" : "overflow-hidden"}`}
      style={{ colorScheme: "light" }}
    >
      {children}
    </div>
  );
}
