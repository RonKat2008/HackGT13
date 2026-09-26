import { redirect } from "next/navigation";
import { createRun, type Product } from "@/lib/api";

async function startRun(formData: FormData) {
  "use server";

  const goal = String(formData.get("goal") ?? "").trim();
  const product = String(formData.get("product") ?? "") as Product;
  const fixture = formData.get("fixture") === "on";

  if (!goal) {
    redirect(`/?error=${encodeURIComponent("Goal is required.")}`);
  }
  if (product !== "stormcite" && product !== "landfall") {
    redirect(`/?error=${encodeURIComponent("Product must be stormcite or landfall.")}`);
  }

  let run;
  try {
    run = await createRun({ product, goal, fixture });
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Failed to start run.";
    redirect(`/?error=${encodeURIComponent(message)}`);
  }
  redirect(`/runs/${run.run_id}`);
}

export default async function Home({ searchParams }: PageProps<"/">) {
  const params = await searchParams;
  const rawError = params.error;
  const error =
    typeof rawError === "string"
      ? rawError
      : Array.isArray(rawError)
        ? rawError[0]
        : undefined;

  return (
    <main className="mx-auto flex w-full max-w-lg flex-1 flex-col justify-center px-6 py-16">
      <h1 className="mb-8 text-2xl font-semibold tracking-tight text-zinc-900">
        Start a run
      </h1>

      {error ? (
        <p
          role="alert"
          className="mb-6 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
        >
          {error}
        </p>
      ) : null}

      <form action={startRun} className="flex flex-col gap-6">
        <div className="flex flex-col gap-2">
          <label htmlFor="goal" className="text-sm font-medium text-zinc-700">
            Goal
          </label>
          <textarea
            id="goal"
            name="goal"
            required
            rows={4}
            className="rounded border border-zinc-300 px-3 py-2 text-zinc-900 shadow-sm focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
          />
        </div>

        <div className="flex flex-col gap-2">
          <label
            htmlFor="product"
            className="text-sm font-medium text-zinc-700"
          >
            Product
          </label>
          <select
            id="product"
            name="product"
            required
            defaultValue="stormcite"
            className="rounded border border-zinc-300 px-3 py-2 text-zinc-900 shadow-sm focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
          >
            <option value="stormcite">stormcite</option>
            <option value="landfall">landfall</option>
          </select>
        </div>

        <div className="flex items-center gap-2">
          <input
            id="fixture"
            name="fixture"
            type="checkbox"
            className="size-4 rounded border-zinc-300 text-zinc-900 focus:ring-zinc-500"
          />
          <label htmlFor="fixture" className="text-sm font-medium text-zinc-700">
            Fixture
          </label>
        </div>

        <button
          type="submit"
          className="rounded bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 focus:outline-none focus:ring-2 focus:ring-zinc-500 focus:ring-offset-2"
        >
          Start run
        </button>
      </form>
    </main>
  );
}
