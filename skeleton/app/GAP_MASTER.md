# Multi-Gap Starter Master Index

Branch: `grok/gap-security-assets-20261022`

## Core Starters (10 gaps)

- `skeleton/security/path_url_hardener.py` + `vault_path_wiring.py`
- `skeleton/forge/pipelines/commercial_asset_starter.py`
- `skeleton/distributed/mesh/multiplayer_authority.py`
- `skeleton/knowledge/graphs/sheaf_facade.py`
- `skeleton/native/emulation_mapping.py`
- `skeleton/ai/runtime/weight_candidate_loop.py`
- `skeleton/simulation/platform/visual_verification.py`
- `skeleton/simulation/game/driving_kinematic.py`
- `skeleton/foundation/architecture/genos_cutover.py`
- `skeleton/repo_machine/shim_audit.py`

## Orchestration & Operator Surface

- `skeleton/app/gap_orchestrator.py`
- `skeleton/app/gap_cli.py`
- `skeleton/app/gap_status.py`
- `skeleton/app/gap_health.py`
- `skeleton/app/gap_metrics.py`
- `skeleton/app/gap_routes.py`
- `skeleton/app/gap_probe.py`
- `skeleton/app/gap_ci.py`
- `skeleton/app/gap_evidence.py`

## Documentation

- `skeleton/app/GAP_STARTERS.md`
- `skeleton/app/GAP_DEPLOY.md`
- `skeleton/app/GAP_MASTER.md` (this file)

## Tests

All `skeleton/testing/test_gap_*.py` and related plane tests.

## Invariants

- stored_prose=0 on every card
- Fail-closed on all negative paths
- Provenance receipts on every success
- No stubs, no TODO, no false claims
- All 10 planes must report before ready=true

## Verification

```bash
python -m skeleton.app.gap_ci
python -m pytest skeleton/testing/test_gap_*.py -q
```

Packet is complete, receipted, and CI-verifiable.
