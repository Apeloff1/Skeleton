# Byte-identical module inventory (issue #80)

The consolidation program moved many packages under new homes, chiefly `skeleton/ai/**`, but the old locations still carry **full byte-for-byte copies** rather than thin re-export shims. On `main` today there are **2453 groups of identical Python modules covering 4913 files** in the canonical tree. `satellites/branch-snapshots/`, `__init__.py`, fixtures, and files under 200 bytes are excluded.

These clones can't be found by the existing consolidation gates:

- `scripts/check_legacy_duplicate_inventory.py` (#969) fingerprints duplicate *contracts* in a few scan roots.
- `scripts/check_compat_shim_inventory.py` (#1035) tracks filename-level compatibility shims.

Whole-file clones fall between the two. The risk is drift: a fix lands in one copy, callers of the other copy keep the bug, and nothing fails.

## The checker

`scripts/check_byte_identical_modules.py` is read-only and stdlib-only.

```bash
python3 scripts/check_byte_identical_modules.py            # check against baseline
python3 scripts/check_byte_identical_modules.py --json     # machine-readable result
python3 scripts/check_byte_identical_modules.py --write-baseline   # after a reviewed consolidation
```

It works as a ratchet against `docs/consolidation/byte_identical_modules.baseline.json`:

- A **new** clone group fails the check. To share code, import from the canonical module or add a re-export shim instead of copying.
- A group that **shrinks or disappears** is reported as progress and never fails. Rewrite the baseline in the same PR that removes clones.

`tests/test_byte_identical_module_inventory.py` covers the grouping and ratchet logic and asserts that the repo matches the committed baseline. It isn't wired into required checks, because merge policy is owned by #127.

## Largest clone families

Top 30 directory pairs by number of identical modules:

| Directory pair | Identical modules |
|---|---|
| `skeleton/ai/shell/` ↔ `skeleton/shells/ai/` | 150 |
| `skeleton/ai/agents/` ↔ `skeleton/jeeves/agent/` | 110 |
| `skeleton/ai/runtime/` ↔ `skeleton/kernel/ops/` | 98 |
| `skeleton/ai/agents/` ↔ `skeleton/automation/agents/` | 67 |
| `skeleton/ai/runtime/` ↔ `skeleton/app/runtime/` | 50 |
| `backend/gameforge/exocortex/` ↔ `skeleton/ai/research/` | 40 |
| `skeleton/ai/simulation/` ↔ `skeleton/simulation/ecs/` | 39 |
| `skeleton/ai/learning/` ↔ `skeleton/learning/school/` | 33 |
| `skeleton/ai/build/` ↔ `skeleton/automation/shift_supervisor/` | 28 |
| `skeleton/ai/runtime/` ↔ `skeleton/distributed/galaxy/` | 26 |
| `skeleton/ai/simulation/` ↔ `skeleton/simulation/physics/` | 26 |
| `skeleton/ai/runtime/` ↔ `skeleton/kernel/omnifabric/` | 21 |
| `skeleton/ai/research/` ↔ `skeleton/foundation/architecture/` | 21 |
| `skeleton/ai/agents/` ↔ `skeleton/automation/swarm/` | 20 |
| `skeleton/ai/forge/` ↔ `skeleton/forge/pipelines/` | 18 |
| `backend/gameforge/personal/` ↔ `skeleton/ai/research/` | 18 |
| `skeleton/ai/runtime/` ↔ `skeleton/frontier/runtime/` | 16 |
| `skeleton/ai/runtime/` ↔ `skeleton/automation/overseer/` | 15 |
| `skeleton/ai/build/` ↔ `skeleton/pr_automation/runner_hygiene/` | 13 |
| `skeleton/ai/runtime/` ↔ `skeleton/cortex/pack_c/` | 13 |
| `skeleton/ai/runtime/` ↔ `skeleton/knowledge/graphs/` | 12 |
| `skeleton/ai/runtime/` ↔ `skeleton/frontier/progression/` | 12 |
| `backend/gameforge/agents/` ↔ `skeleton/ai/research/` | 11 |
| `skeleton/ai/research/` ↔ `skeleton/research/social/` | 10 |
| `backend/gameforge/math_exocortex/` ↔ `skeleton/ai/research/` | 10 |
| `skeleton/ai/runtime/` ↔ `skeleton/distributed/mesh/` | 10 |
| `skeleton/ai/simulation/` ↔ `skeleton/simulation/game/` | 10 |
| `backend/gameforge/jeeves/` ↔ `skeleton/ai/research/` | 9 |
| `skeleton/ai/runtime/` ↔ `skeleton/frontier/ecology/` | 8 |
| `skeleton/ai/runtime/` ↔ `skeleton/frontier/economy/` | 8 |

## Suggested burn-down order

1. Pick a family from the table and choose the canonical side. The `skeleton/ai/**` side is canonical per `docs/CANONICAL_MODULE_BOUNDARIES.md`, unless that doc says otherwise.
2. Replace each non-canonical copy with a re-export shim (`from skeleton.ai.<pkg>.<mod> import *` plus explicit names) so existing imports keep working. Then register the shim with the compat shim inventory (#1035).
3. Run the family's tests, rewrite the baseline, and land one family per PR so each diff stays reviewable.

No files are moved or deleted by this change.
