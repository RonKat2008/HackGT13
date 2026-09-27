# PreSearch screen

Next.js app for the chair desk (`/desk`) and the author desk (`/author`). Sign-in is Supabase. The browser never holds `XAI_API_KEY`, `OPENROUTER_API_KEY`, or the Supabase service role key.

Setup, env files, and how the checker starts are in the [repository README](../../README.md).

```bash
npm install
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000). The app reads `apps/web/.env.local`:

```
SUPABASE_URL=
SUPABASE_PUBLISHABLE_KEY=
ORCHESTRATOR_URL=http://127.0.0.1:8000
```
