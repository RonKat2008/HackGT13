"use client";

import { usePathname } from "next/navigation";

export function Stage({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  return (
    <div key={path} className="desk-rise flex min-h-0 min-w-0 flex-1 flex-col">
      {children}
    </div>
  );
}
