# Spine bind recovery checkpoint

This runbook describes the P2 bind/recovery evidence tranche on branch feat/p2-runtime-spine.

## Boundary

The checkpoint path is evidence only. It does not start the runtime dispatcher,
does not import or bootstrap Motor, does not fill unread sequence gaps, does not
claim provider-surface or PR Automation state, does not mark CI green, and does
not merge or sign off P2.

The authoritative blockers remain explicit:

- apply is not landed
- provider surface is unclaimed
- PR Automation is unclaimed
- CI green is unread
- merge is unread
- Motor remains unwired
- the runtime dispatcher remains unwired by this lane

## Sequence

1. Produce a sealed dark bind card and bind hash chain.
2. Join the bind card to the unread gap and unread external surfaces.
3. Build a deterministic SpineBindSnapshot.
4. Derive SpineBindRecovery. Its ready and activated fields remain false.
5. Append one SpineBindCheckpoint per tenant.
6. Replay the checkpoint and verify the row count is unchanged.
7. Read the checkpoint through SpineBindCheckpointTenant and verify foreign
   tenants remain invisible.
8. Seal the checkpoint rows with SpineBindCheckpointChain.
9. Join checkpoint, replay, tenant read, and chain into SpineBindBundle.
10. Verify the bundle digest with SpineBindBundleVerify.

## Failure behavior

Any of the following fails closed:

- bind/surface/gap tenant mismatch
- claimed or green provider/PR surface
- filled unread sequence gap
- rewritten bind or checkpoint digest
- promoted checkpoint flags
- replay row insertion
- foreign-tenant visibility
- bundle digest mutation

A green focused test run verifies these invariants only. It is not completion,
promotion, maturity, activation, implementation sign-off, or verification
sign-off.

## Focused tests

python -m pytest -q skeleton/testing/test_spine_bind_snapshot.py skeleton/testing/test_spine_bind_checkpoint.py skeleton/testing/test_spine_bind_bundle.py skeleton/testing/test_spine_manifest.py skeleton/testing/test_spine_masterplan.py

## Exact-head control

The State Recovery Drill workflow runs the focused bind recovery regressions and
scripts/check_spine_bind_recovery.py on the exact pull-request head. The control
fails closed when a canonical persistence file differs from its AI-tree mirror,
when the manifest is not exactly 57 unique seams, when any recovery seam law is
missing or changed, or when the masterplan no longer records the 75% bind-card
evidence state and no-activation boundary.

The control report is evidence about repository consistency only. valid=true is
not runtime activation, provider/PR surface promotion, CI completion authority,
merge authority, or a P2 sign-off.


## Destructive-scratch restore drill

The recovery workflow also executes:

python scripts/state_recovery_drill.py live-spine-bind-sqlite \
  --workdir <scratch>/skeleton_recovery_drill_spine_bind

The drill creates a real SpineBindCheckpoint SQLite database, captures a
transactionally consistent backup through SQLite's backup API, deletes the
source authority, restores into a fresh database, verifies schema/data digests,
replays the checkpoint without insertion, proves a foreign tenant is empty,
recomputes the checkpoint hash chain, and verifies the final evidence bundle.

Every activation-bearing flag remains false after restore. The drill rejects
digest drift, row-count drift, replay insertion, tenant leakage, chain rewrite,
or any accidental activation. It uses only scratch directories whose basename
starts with skeleton_recovery_drill_.
