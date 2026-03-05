-- Optimize fetch_urls.py query on items table
-- Target query shape:
--   where listing_status = 'Active'
--     and stocking_url is not null
--
-- Execute in Supabase SQL Editor.

create index if not exists idx_items_listing_status_stocking_url_not_null
  on public.items using btree (listing_status, stocking_url)
  where stocking_url is not null;

-- Optional: if many empty strings exist and you start filtering them in query
-- (e.g. stocking_url=not.eq.''), this index helps that pattern too.
create index if not exists idx_items_listing_status_stocking_url_non_empty
  on public.items using btree (listing_status, stocking_url)
  where stocking_url is not null and stocking_url <> '';
