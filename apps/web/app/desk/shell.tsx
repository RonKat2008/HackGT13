import { Stage } from "./stage";

export function DeskShell({
  rail,
  children,
}: {
  rail: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col lg:grid lg:grid-cols-[15.5rem_minmax(0,1fr)]">
      {rail}
      <Stage>{children}</Stage>
    </div>
  );
}
