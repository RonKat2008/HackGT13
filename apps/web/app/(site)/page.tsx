import Link from "next/link";
import { DeskStill, Films } from "./films";

const steps = [
  {
    name: "Make a list",
    text: "A conference is a list of papers you are responsible for. Add the arXiv ids, then run the queue.",
  },
  {
    name: "Ask",
    text: "The thread is the desk. Name a paper with @ and ask what failed. The reply stays tied to that paper.",
  },
  {
    name: "Read",
    text: "Open the paper. The sentence that failed is marked, and the reason sits beside it.",
  },
];

export default function HomePage() {
  return (
    <main>
      <section className="mx-auto grid max-w-6xl items-center gap-12 px-6 py-16 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] lg:py-24">
        <div>
          <p className="text-[11px] tracking-[0.18em] text-[#8c3a2f]">FOR CONFERENCE CHAIRS</p>
          <h1 className="mt-4 font-[family-name:var(--desk-serif)] text-6xl leading-[0.95] tracking-tight sm:text-7xl">
            A quiet desk
          </h1>
          <p className="mt-6 max-w-md border-l border-[#c4a15a] pl-4 text-lg leading-8 text-[#1c1915]">
            for the papers a chair is responsible for.
          </p>
          <div className="mt-10 flex flex-wrap items-center gap-4">
            <Link href="/signup" className="rounded-full bg-[#1c1915] px-5 py-3 text-sm text-[#f4f0e6]">
              Create account
            </Link>
            <Link href="#how" className="text-sm underline decoration-[#c4a15a] underline-offset-4">
              Watch how it works
            </Link>
          </div>
        </div>
        <DeskStill />
      </section>

      <section id="how" className="mx-auto max-w-6xl px-6 pb-20">
        <p className="text-[11px] tracking-[0.18em] text-[#8c3a2f]">HOW IT WORKS</p>
        <h2 className="mt-3 max-w-xl font-[family-name:var(--desk-serif)] text-4xl leading-tight">
          Three quiet passes over the same list.
        </h2>
        <div className="mt-12">
          <Films />
        </div>
        <ol className="mt-16 grid gap-10 border-t border-[#e4dcd0] pt-10 md:grid-cols-3">
          {steps.map((step, index) => (
            <li key={step.name}>
              <p className="text-[11px] tracking-[0.16em] text-[#6b645c]">0{index + 1}</p>
              <h3 className="mt-2 font-[family-name:var(--desk-serif)] text-2xl">{step.name}</h3>
              <p className="mt-3 text-sm leading-6 text-[#6b645c]">{step.text}</p>
            </li>
          ))}
        </ol>
        <p className="mt-12 max-w-2xl text-sm leading-7 text-[#1c1915]">
          An issue is a failed citation, a number missing from the results, weak support, or a failed rerun.
          A likeness score is not a verdict. Shelf labels are Human or Generated.
        </p>
      </section>

      <footer className="border-t border-[#e4dcd0]">
        <div className="mx-auto flex max-w-6xl flex-wrap items-end justify-between gap-6 px-6 py-12">
          <div>
            <p className="font-[family-name:var(--desk-serif)] text-3xl">ArxAudit</p>
            <p className="mt-2 text-sm text-[#6b645c]">Open the desk when the list is yours.</p>
          </div>
          <Link href="/login" className="rounded-full bg-[#1c1915] px-5 py-3 text-sm text-[#f4f0e6]">
            Sign in
          </Link>
        </div>
      </footer>
    </main>
  );
}
