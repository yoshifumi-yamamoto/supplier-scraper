create table if not exists public.scrape_run_steps (
  id uuid not null default gen_random_uuid(),
  run_id uuid not null,
  step_name text not null,
  status text not null check (status in ('queued', 'running', 'success', 'failed')),
  started_at timestamptz not null default now(),
  finished_at timestamptz null,
  message text null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint scrape_run_steps_pkey primary key (id),
  constraint scrape_run_steps_run_id_fkey foreign key (run_id)
    references public.scrape_runs (id) on delete cascade
);

create index if not exists idx_scrape_run_steps_run_id
  on public.scrape_run_steps using btree (run_id, started_at asc);
