# Source Integration Status

## Current State
- Unified runtime is centralized in:
  - `apps/runner`
  - `apps/mcp_server`
  - `apps/validator_agent`
- Site dispatch is now centralized in:
  - `scrapers/sites/registry.py`
- Common legacy execution flow is centralized in:
  - `scrapers/common/legacy_pipeline.py`

## Sites Registered
- `yahoofleama` (active)
- `secondstreet` (active)
- `mercari` (copied)
- `rakuma` (copied)
- `yafuoku` (copied)
- `yodobashi` (copied)
- `hardoff` (copied)
- `rakuten` (API monitoring path)

## Migration Meaning
- `active`: legacy directory exists in integrated repo and is already used in production cron.
- `copied`: legacy directory was copied and can be run from unified runner, but not yet enabled in production cron.
- `registered`: site is in registry but legacy scripts are not copied yet.

## Next Steps To Complete Full Source Integration
1. Run per-site smoke test:
   - `PYTHONPATH=. python apps/runner/main.py --site <site>`
2. Add site-specific cron slots after smoke tests pass.
3. Remove old standalone repo execution paths.

## Remaining Work For Full Migration

### 1. Server runtime still depends on old `baysync-*` paths
- Current cron already uses `/root/supplier-scraper-main`.
- But current systemd still loads env from old path:
  - `/etc/systemd/system/supplier-mcp.service`
  - `EnvironmentFile=/root/baysync-yodobashi-stock-scraper/.env`
- Old runtime directories still exist on KAGOYA:
  - `/root/baysync-mercari-stock-scraper`
  - `/root/baysync-yafuoku-stock-scraper`
  - `/root/baysync-yahoofleama-stock-scraper`
  - `/root/baysync-hardoff-stock-scraper`
  - `/root/baysync-rakuma-stock-scraper`
  - `/root/baysync-yodobashi-stock-scraper`
  - `/root/baysync-2ndstreet-stock-scraper`

### 2. Integrated repo still hardcodes old server paths
- `docs/mcp-server.md`
  - still references `/root/baysync-yodobashi-stock-scraper/.env`
  - still documents `run_all_scrapes.sh`
- `scripts/mcp_run_site.sh`
  - still checks `/root/run_all_scrapes.sh`
- `scrapers/common/execution_guard.py`
  - still cleans `/root/baysync-{site}-stock-scraper/tmp_chrome`
- Legacy launcher scripts still `cd` into old directories:
  - `legacy/mercari/run_scrape.sh`
  - `legacy/yafuoku/run_scrape.sh`
  - `legacy/yahoofleama/run_scrape.sh`
  - `legacy/hardoff/run_scrape.sh`
  - `legacy/rakuma/run_scrape.sh`
  - `legacy/yodobashi/run_scrape.sh`
- `legacy/mercari/run_all_scrapes.sh`
  - still orchestrates old `/root/baysync-*` directories

### 3. Production alignment is incomplete for Mercari
- On KAGOYA, `supplier-scraper-main/legacy/yafuoku` and `legacy/yahoofleama` match old server copies.
- Mercari was hotfixed in `/root/baysync-mercari-stock-scraper`, so `/root/supplier-scraper-main/legacy/mercari` is not yet guaranteed to match the live hotfix state.
- Before deleting old server directories, Mercari changes need to be ported into `/root/supplier-scraper-main/legacy/mercari` and redeployed there.

### 4. Old local repo is now archive-only candidate
- Local old repo: `/Users/yamamotoyoshifumi/projects/ebay/supplier-scraper`
- It still contains:
  - old standalone repos per site
  - nested `.git` directories
  - logs / html dumps / sample CSVs
  - old docs such as `docs/ssh-access.md` and `docs/kagoya-hotfix-2026-03-04.md`
- It should not be deleted until server references in this repo are removed.

## Recommended Migration Order
1. Move server env loading from old `baysync-*` path to `/root/supplier-scraper-main/.env` or another shared env path.
2. Replace all hardcoded `/root/baysync-*` references in this repo with `/root/supplier-scraper-main/...`.
3. Port the Mercari hotfix into `legacy/mercari` inside this repo.
4. Deploy updated `supplier-scraper-main` to KAGOYA and verify:
   - `supplier-mcp.service`
   - `mcp_orchestrator.sh`
   - manual run per migrated site
5. Disable dependence on `/root/run_all_scrapes.sh`.
6. Archive old local `supplier-scraper`.
7. Remove old `/root/baysync-*` directories on KAGOYA only after verification.
