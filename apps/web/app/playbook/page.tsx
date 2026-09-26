import { getPlaybook, type Patch, type Product } from "@/lib/api";

type ProductResult =
  | { product: Product; patches: Patch[]; error: null }
  | { product: Product; patches: null; error: string };

async function loadProduct(product: Product): Promise<ProductResult> {
  try {
    const patches = await getPlaybook(product);
    return { product, patches, error: null };
  } catch (err) {
    return {
      product,
      patches: null,
      error: err instanceof Error ? err.message : "Failed to load playbook.",
    };
  }
}

function groupByStatus(patches: Patch[]) {
  const live: Patch[] = [];
  const archived: Patch[] = [];
  const draft: Patch[] = [];
  for (const patch of patches) {
    if (patch.status === "live") live.push(patch);
    else if (patch.status === "archived") archived.push(patch);
    else draft.push(patch);
  }
  return { live, archived, draft };
}

function PatchList({
  title,
  patches,
}: {
  title: string;
  patches: Patch[];
}) {
  if (patches.length === 0) {
    return (
      <div className="mt-6">
        <h3 className="mb-2 text-sm font-medium text-zinc-700">{title}</h3>
        <p className="text-sm text-zinc-600">None.</p>
      </div>
    );
  }

  return (
    <div className="mt-6">
      <h3 className="mb-3 text-sm font-medium text-zinc-700">{title}</h3>
      <ul className="flex flex-col gap-4 text-sm">
        {patches.map((patch) => (
          <li
            key={patch.id}
            className="border-b border-zinc-100 pb-4 last:border-b-0"
          >
            <p className="font-medium text-zinc-900">{patch.kind}</p>
            <p className="mt-1 text-zinc-700">{patch.body}</p>
            <dl className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-zinc-600">
              <div>
                <dt className="inline font-medium text-zinc-700">wins: </dt>
                <dd className="inline">{patch.wins}</dd>
              </div>
              <div>
                <dt className="inline font-medium text-zinc-700">losses: </dt>
                <dd className="inline">{patch.losses}</dd>
              </div>
              <div>
                <dt className="inline font-medium text-zinc-700">
                  fitness_ema:{" "}
                </dt>
                <dd className="inline">{patch.fitness_ema}</dd>
              </div>
            </dl>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ProductSection({ result }: { result: ProductResult }) {
  const groups = result.patches ? groupByStatus(result.patches) : null;

  return (
    <section className="mt-12 first:mt-0">
      <h2 className="text-lg font-semibold tracking-tight text-zinc-900 capitalize">
        {result.product}
      </h2>
      {result.error ? (
        <p
          role="alert"
          className="mt-4 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
        >
          {result.error}
        </p>
      ) : null}
      {groups ? (
        <>
          <PatchList title="Live" patches={groups.live} />
          <PatchList title="Archived" patches={groups.archived} />
          {groups.draft.length > 0 ? (
            <PatchList title="Draft" patches={groups.draft} />
          ) : null}
        </>
      ) : null}
    </section>
  );
}

export default async function PlaybookPage() {
  const [stormcite, landfall] = await Promise.all([
    loadProduct("stormcite"),
    loadProduct("landfall"),
  ]);

  return (
    <main className="mx-auto flex w-full max-w-lg flex-1 flex-col px-6 py-16">
      <h1 className="mb-8 text-2xl font-semibold tracking-tight text-zinc-900">
        Playbook
      </h1>
      <ProductSection result={stormcite} />
      <ProductSection result={landfall} />
    </main>
  );
}
