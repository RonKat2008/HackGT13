import { redirect } from "next/navigation";
import { createRun, type Product } from "@/lib/api";

async function startRun(formData: FormData) {
  "use server";

  const goal = String(formData.get("goal") ?? "").trim();
  const product = String(formData.get("product") ?? "") as Product;
  const fixture = formData.get("fixture") === "on";

  if (!goal) {
    redirect(`/start?error=${encodeURIComponent("Goal is required.")}`);
  }
  if (product !== "stormcite" && product !== "landfall" && product !== "arxaudit") {
    redirect(`/start?error=${encodeURIComponent("Product must be stormcite, landfall, or arxaudit.")}`);
  }

  let run;
  try {
    run = await createRun({ product, goal, fixture });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Failed to start run.";
    redirect(`/start?error=${encodeURIComponent(message)}`);
  }
  redirect(`/runs/${run.run_id}`);
}

export default async function StartPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const params = await searchParams;
  const error = typeof params.error === "string" ? params.error : undefined;

  return (
    <main className="mx-auto flex w-full max-w-lg flex-1 flex-col px-6 py-16">
      <p className="text-[11px] tracking-[0.16em] text-[#8c3a2f]">OPERATOR</p>
      <h1 className="mt-3 font-[family-name:var(--desk-serif)] text-4xl">Start a run</h1>
      {error ? (
        <p role="alert" className="mt-6 text-sm text-[#8c3a2f]">
          {error}
        </p>
      ) : null}
      <form action={startRun} className="mt-8 flex flex-col gap-5">
        <label className="flex flex-col gap-1 text-sm">
          Goal
          <textarea
            name="goal"
            required
            rows={4}
            className="rounded-2xl bg-white px-4 py-3 outline-none ring-[#e4dcd0] focus-visible:ring-2"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Product
          <select
            name="product"
            required
            defaultValue="arxaudit"
            className="rounded-2xl bg-white px-4 py-3 outline-none"
          >
            <option value="arxaudit">arxaudit</option>
            <option value="stormcite">stormcite</option>
            <option value="landfall">landfall</option>
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input name="fixture" type="checkbox" className="size-4" />
          Fixture
        </label>
        <button className="w-fit rounded-full bg-[#1c1915] px-5 py-3 text-sm text-[#f4f0e6]" type="submit">
          Start run
        </button>
      </form>
    </main>
  );
}
