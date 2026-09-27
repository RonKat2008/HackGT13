import paper from "./fixtures/paper.json";
import { PaperPanel } from "./paper-panel";

export default function AuthorPage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <PaperPanel paper={paper} />
    </main>
  );
}
