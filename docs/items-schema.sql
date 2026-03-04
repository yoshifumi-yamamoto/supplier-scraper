create table public.items (
  id uuid not null default gen_random_uuid (),
  ebay_account_id uuid null,
  ebay_user_id text not null,
  ebay_item_id text not null,
  listing_status text null,
  synced_at timestamp with time zone null,
  sku text null,
  stocking_url text null,
  title text null,
  cost_price numeric null,
  shipping_cost numeric null,
  price numeric null,
  qty integer null,
  scraped_stock_status text null,
  scraped_updated_at timestamp with time zone null,
  researcher text null,
  exhibitor text null,
  research_date date null,
  exhibit_date date null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  deleted_at timestamp with time zone null,
  last_seen_at timestamp with time zone null,
  listing_state text null default 'ACTIVE'::text,
  listing_state_updated_at timestamp without time zone null default now(),
  system_account_id uuid null,
  item_sheet_synced_at timestamp with time zone null,
  image_url text null,
  sync_enabled boolean null default true,
  is_scraped boolean null default false,
  constraint items_pkey primary key (id),
  constraint items_ebay_item_id_key unique (ebay_item_id),
  constraint items_ebay_unique unique (ebay_item_id, ebay_account_id),
  constraint items_ebay_account_id_fkey foreign KEY (ebay_account_id) references ebay_accounts (id) on delete CASCADE,
  constraint items_system_account_id_fkey foreign KEY (system_account_id) references system_accounts (id)
) TABLESPACE pg_default;

create index IF not exists items_active_user_stocking_url_idx on public.items using btree (ebay_user_id, stocking_url) TABLESPACE pg_default
where
  (listing_status = 'Active'::text);

create index IF not exists idx_items_account_status_created_at on public.items using btree (
  system_account_id,
  listing_status,
  created_at desc,
  id
) TABLESPACE pg_default;
