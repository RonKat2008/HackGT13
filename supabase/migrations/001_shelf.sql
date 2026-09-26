create extension if not exists vector;

create table reference_items (
  id uuid primary key default gen_random_uuid(),
  source text,
  external_id text,
  title text,
  abstract text,
  label text check (label in ('human', 'ai')),
  domain text,
  embedding vector(384),
  unique (source, external_id)
);

create table probe_meta (
  singleton boolean primary key default true check (singleton),
  auc double precision,
  n_rows integer,
  hidden boolean,
  trained_at timestamptz
);

create table conferences (
  conference_id uuid primary key default gen_random_uuid(),
  name text not null,
  contact_email text
);

create table batches (
  batch_id uuid primary key default gen_random_uuid(),
  kind text check (kind in ('links', 'batch')),
  name text,
  conference_id uuid references conferences,
  arxiv_ids text[] not null,
  created_at timestamptz default now()
);

create table paper_jobs (
  job_id uuid primary key default gen_random_uuid(),
  batch_id uuid references batches,
  arxiv_id text,
  run_id uuid,
  status text,
  specialist text,
  fitness double precision,
  issue_count integer default 0,
  author_name text,
  author_email text,
  contacted_at timestamptz
);

create table job_events (
  event_id uuid primary key default gen_random_uuid(),
  job_id uuid references paper_jobs,
  specialist text,
  state text check (state in ('started', 'finished', 'failed')),
  detail text,
  created_at timestamptz default now()
);

alter publication supabase_realtime add table paper_jobs;
alter publication supabase_realtime add table job_events;

alter table reference_items enable row level security;
alter table probe_meta enable row level security;
alter table conferences enable row level security;
alter table batches enable row level security;
alter table paper_jobs enable row level security;
alter table job_events enable row level security;

create policy "reference_items_select_anon"
  on reference_items for select to anon using (true);

create policy "paper_jobs_select_anon"
  on paper_jobs for select to anon using (true);

create policy "job_events_select_anon"
  on job_events for select to anon using (true);
