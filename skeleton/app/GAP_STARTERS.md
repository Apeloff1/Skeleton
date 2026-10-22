# Multi-Gap Starter Packet

Branch: `grok/gap-security-assets-20261022`

All 10 large gaps identified in the 2026-10-22 scan now have fail-closed starter modules plus a unified orchestrator.

## Modules

| Gap | Module | Guarantee |
|-----|--------|-----------|
| #9 Security | `skeleton/security/path_url_hardener.py` | Path confinement + URL allow-list + receipts |
| #1 Assets | `skeleton/forge/pipelines/commercial_asset_starter.py` | Full PNG + Godot .tres + coverage |
| #2 Multiplayer | `skeleton/distributed/mesh/multiplayer_authority.py` | Vector-clock grants, TTL, verify |
| #5 Research | `skeleton/knowledge/graphs/sheaf_facade.py` | Thin facade, lineage card |
| #3 Emulation | `skeleton/native/emulation_mapping.py` | Target qualify, no false success |
| #6 Weights | `skeleton/ai/runtime/weight_candidate_loop.py` | Admit/eval/rollback, never auto-promote |
| #7 Visual | `skeleton/simulation/platform/visual_verification.py` | Binding receipt, no false engine claim |
| #8 Driving | `skeleton/simulation/game/driving_kinematic.py` | Bounded kinematic step |
| #4 Runtimes | `skeleton/foundation/architecture/genos_cutover.py` | Ownership card, explicit bind |
| #10 Shims | `skeleton/repo_machine/shim_audit.py` | Inventory + migration receipt |

## Orchestrator

`skeleton/app/gap_orchestrator.py` → `run_all_starters()` invokes every plane and emits one digest.

## Invariants

- stored_prose=0 on every card
- Fail-closed on all negative paths
- Provenance receipts on every success
- No stubs, no TODO, no false claims

## Next

Wire into live vault sites, studio routes, and exact-head CI. Deepen any plane with full production logic.
