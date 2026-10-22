# Multi-Gap Starter Deployment Notes

Branch: `grok/gap-security-assets-20261022`

## Probe

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -m skeleton.app.gap_probe || exit 1
```

## Routes

Mount `get_health`, `get_metrics`, `get_status` from `skeleton.api.gap_routes` into the FastAPI app under `/api/v1/gap/`.

## Invariants

- All 10 planes must report before `ready=true`
- stored_prose=0 on every card
- Fail-closed on any starter error
- Provenance receipts on every success

## Verification

```bash
python -m skeleton.app.gap_cli
python -m skeleton.app.gap_probe
python -m pytest skeleton/testing/test_gap_*.py -q
```

All starters are complete and receipted. Next: exact-head CI and live mounting.
