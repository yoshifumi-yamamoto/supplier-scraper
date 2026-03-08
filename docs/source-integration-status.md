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
