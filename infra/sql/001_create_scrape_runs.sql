create table if not exists public.scrape_runs (
  id uuid not null,
  site text not null,
  status text not null check (status in ('queued', 'running', 'success', 'failed')),
  trigger_type text not null default 'manual',
  started_at timestamptz not null default now(),
  finished_at timestamptz null,
  error_summary text null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint scrape_runs_pkey primary key (id)
);

create index if not exists idx_scrape_runs_site_started_at
  on public.scrape_runs using btree (site, started_at desc);

create index if not exists idx_scrape_runs_status_started_at
  on public.scrape_runs using btree (status, started_at desc);
