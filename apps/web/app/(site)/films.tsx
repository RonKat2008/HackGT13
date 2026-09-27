function Window({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <figure className="overflow-hidden rounded-2xl bg-[#f7f3ea] ring-1 ring-[#e4dcd0]">
      <figcaption className="sr-only">{label}</figcaption>
      <div className="flex items-center gap-1.5 border-b border-[#e4dcd0] px-4 py-3">
        <span className="size-1.5 rounded-full bg-[#c4a15a]" />
        <span className="text-[11px] tracking-[0.14em] text-[#6b645c]">{label}</span>
      </div>
      <div className="min-h-64 p-5">{children}</div>
    </figure>
  );
}

export function Films() {
  return (
    <div className="grid gap-8 lg:grid-cols-3">
      <div>
        <Window label="Make a list">
          <p className="font-[family-name:var(--desk-serif)] text-xl">Desk review</p>
          <p className="film-beat film-d1 mt-4 rounded-xl bg-white px-3 py-2 font-mono text-xs text-[#6b645c]">
            0000.00001
            <br />
            0000.00002
          </p>
          <ul className="mt-4 space-y-2 text-sm">
            <li className="film-beat film-d2 flex items-center gap-2">
              <span className="size-1.5 rounded-full bg-[#8c3a2f]" />
              Unresolved Citation Paper
            </li>
            <li className="film-beat film-d3 flex items-center gap-2">
              <span className="size-1.5 rounded-full bg-[#2f6b4f]" />
              Measured Metric Paper
            </li>
          </ul>
        </Window>
        <p className="mt-4 text-sm leading-6 text-[#6b645c]">
          Add the arXiv ids. The list stays on your account.
        </p>
      </div>
      <div>
        <Window label="Ask">
          <p className="film-beat film-d1 ml-auto max-w-[14rem] rounded-2xl bg-[#1c1915] px-3 py-2 text-xs leading-5 text-[#f4f0e6]">
            What did the paper claim?
          </p>
          <p className="film-beat film-d3 mt-5 border-l border-[#c4a15a] pl-3 text-sm leading-6">
            The citation (Smith, 2099) does not appear in the references.
          </p>
        </Window>
        <p className="mt-4 text-sm leading-6 text-[#6b645c]">
          Name a paper with @. The desk answers from the audit, not from a score.
        </p>
      </div>
      <div>
        <Window label="Read">
          <p className="font-[family-name:var(--desk-serif)] text-xl leading-tight">
            Unresolved Citation Paper
          </p>
          <p className="film-beat film-d2 mt-4 bg-[#f3e6c8] px-3 py-2 text-sm leading-6">
            Accuracy reached 95.2% on the public benchmark (Smith, 2099).
          </p>
          <p className="film-beat film-d3 mt-3 text-xs leading-5 text-[#6b645c]">
            The number 95.2 in the abstract is absent from the results.
          </p>
        </Window>
        <p className="mt-4 text-sm leading-6 text-[#6b645c]">
          The marked sentence carries the reason.
        </p>
      </div>
    </div>
  );
}

const SHEETS = [
  {
    kicker: "Citation",
    title: "Vaswani et al., 2017",
    body: "The reference resolves in the catalogs.",
    mark: "Resolved",
    tone: "text-[#2f6b4f]",
  },
  {
    kicker: "Number",
    title: "95.2% in the abstract",
    body: "The same figure is absent from the results.",
    mark: "Contradicted",
    tone: "text-[#8c3a2f]",
  },
  {
    kicker: "Needs a person",
    title: "We show the model generalizes",
    body: "Three reads stayed unsure. A chair decides.",
    mark: "Unsettled",
    tone: "text-[#8a6a2f]",
  },
];

export function HeroStage() {
  return (
    <div className="hero-stage" aria-hidden="true">
      <div className="folio">
        <div className="folio-ground" />
        <div className="folio-book">
          {SHEETS.map((sheet, index) => (
            <article key={sheet.kicker} className={`folio-panel folio-panel-${index + 1}`}>
              <p className="text-[11px] tracking-[0.16em] text-[#8c3a2f]">{sheet.kicker}</p>
              <h2 className="mt-3 font-[family-name:var(--desk-serif)] text-xl leading-tight">{sheet.title}</h2>
              <p className="mt-4 text-sm leading-6 text-[#6b645c]">{sheet.body}</p>
              <p className={`mt-6 text-xs ${sheet.tone}`}>{sheet.mark}</p>
            </article>
          ))}
        </div>
      </div>
    </div>
  );
}

export function DeskStill() {
  return (
    <div className="overflow-hidden rounded-[1.75rem] bg-[#f7f3ea] ring-1 ring-[#e4dcd0]" aria-hidden="true">
      <div className="grid min-h-[28rem] sm:grid-cols-[11rem_minmax(0,1fr)]">
        <div className="border-b border-[#e4dcd0] p-5 sm:border-b-0 sm:border-r">
          <p className="font-[family-name:var(--desk-serif)] text-xl">PreSearch</p>
          <p className="mt-6 text-[11px] tracking-[0.16em] text-[#6b645c]">YOUR LISTS</p>
          <p className="mt-4 font-[family-name:var(--desk-serif)] text-lg leading-tight">Desk review</p>
          <p className="mt-1 text-[11px] text-[#6b645c]">2 papers</p>
          <ul className="mt-5 space-y-3 text-sm">
            <li className="flex gap-2">
              <span className="mt-1.5 size-1.5 rounded-full bg-[#8c3a2f]" />
              Unresolved Citation
            </li>
            <li className="flex gap-2">
              <span className="mt-1.5 size-1.5 rounded-full bg-[#2f6b4f]" />
              Measured Metric
            </li>
          </ul>
        </div>
        <div className="grid min-h-0 sm:grid-cols-[minmax(0,1fr)_9rem]">
          <div className="flex flex-col justify-between p-6 sm:p-8">
            <div>
              <p className="text-sm leading-7 text-[#1c1915]">
                Unresolved Citation needs a citation check.
                <button type="button" className="mx-1 rounded-full bg-[#f3e6c8] px-2 py-0.5 text-xs" tabIndex={-1}>
                  [1]
                </button>
              </p>
              <p className="mt-4 max-w-xs border-l border-[#c4a15a] pl-3 text-xs leading-5 text-[#6b645c]">
                Smith, 2099 does not appear in the references.
              </p>
            </div>
            <div className="mt-8 rounded-2xl bg-white px-4 py-3 text-sm text-[#6b645c] ring-1 ring-[#e4dcd0]">
              Ask about a paper. Type @ to name one.
            </div>
          </div>
          <div className="border-t border-[#e4dcd0] bg-white p-4 sm:border-l sm:border-t-0">
            <p className="font-[family-name:var(--desk-serif)] text-sm leading-tight">Unresolved Citation</p>
            <p className="mt-1 text-[11px] text-[#6b645c]">Page 1</p>
            <p className="mt-4 text-[11px] leading-5 text-[#1c1915]">
              Accuracy reached <span className="bg-[#f3e6c8] px-0.5">95.2%</span> (Smith, 2099).
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
