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
- `mercari` (registered)
- `rakuma` (registered)
- `yafuoku` (registered)
- `yodobashi` (registered)
- `hardoff` (registered)
- `rakuten` (API monitoring path)

## Migration Meaning
- `active`: legacy directory exists in integrated repo and is already used in production cron.
- `registered`: site can be selected from runner/MCP but requires copying legacy scripts to `legacy/<site>/`.

## Next Steps To Complete Full Source Integration
1. Copy each site legacy source into integrated repo:
   - `legacy/mercari`
   - `legacy/rakuma`
   - `legacy/yafuoku`
   - `legacy/yodobashi`
   - `legacy/hardoff`
2. Run per-site smoke test:
   - `PYTHONPATH=. python apps/runner/main.py --site <site>`
3. Add site-specific cron slots after smoke tests pass.
4. Remove old standalone repo execution paths.
