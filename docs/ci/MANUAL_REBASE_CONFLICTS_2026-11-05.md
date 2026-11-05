# Manual Rebase Conflicts — 2026-11-05

Automated `update_pull_request_branch` fails with merge conflict on:

1. **#4628** Studio D first playable (~180 paths, below floor)
   - Documentation: fix/studio-d-first-playable-rebase-20261105
   - Dependency on #4585. Manual exact-head rebase required.

2. **#4636** non-finite OBJ vertex rejection
   - Documentation + delta: fix/obj-finite-metadata-rebase-20261105
   - Apply finite check in `_obj` on current main, restore full parsers, exact-head CI.

3. **#4674** scene market delivery (138 paths, below floor)
   - Documentation: fix/scene-market-rebase-20261105
   - Manual exact-head rebase required.

After manual rebase: re-verify tree, run focused tests, exact-head Merge Readiness + Backend Quality + security gates. No automatic resolution. All holds preserved.
