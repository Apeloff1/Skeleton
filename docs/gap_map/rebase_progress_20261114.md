# Rebase progress — 2026-11-14

Companion to docs/GAP_MAP.md. Covers archive/*, recovery/* and reconcile/* branches marked integrate. Picks were replayed with `git merge-tree` onto main c7e29744e.

| Branch | Replay result (picked / conflict / empty / on-main) | Status |
|---|---|---|
| `archive/pre-rebase-mb-gfa-20261113-ce1bf3c1` |  | #5356 |
| `archive/pre-rebase-mb-gf-l-20261113-0fa65b10` |  | #5356 (bundled) |
| `archive/pre-rebase-mb-gf-l-route-repair-20261114-98dc22f` |  | #5356 (bundled) |
| `feat/mb-gfa-wiring-internal-systems-20261031` |  | #5356 (bundled) |
| `feat/mb-gf-l-route-repair-middleware-20261031` |  | #5356 (bundled) |
| `archive/pre-rebase-frontier-chunk-telemetry-20261113-fbe19010` |  | #5357 |
| `archive/pre-rebase-ci-jeeves-contracts-glenny-20261031-20261113-bed41435` |  | #5357 (bundled) |
| `archive/pre-rebase-gf-b040-s4s5-20261113-c6a5a6c7` |  | #5358 |
| `reconcile/flgb-iterative-scene-transform-20261108-r01` |  | #5361 |
| `reconcile/scene-graph-iterative-editor-simulation-20261108-r01` |  | #5361 (bundled) |
| `reconcile/local-ai-native-readiness-failclosed-20261108-r01` |  | #5362 |
| `reconcile/local-ai-truth-loader-runtime-doctor-20261108-r01` |  | #5362 (bundled) |
| `archive/frontier-milestone-14-pre-reconcile-20261023` |  | obsolete: 80,064 generated files |
| `archive/pre-rebase-telemetry-121-20261113-dbb23f65` |  | excluded: #121 lane (#5350) |
| `archive/forge-postepoch-4202-pre-reconcile-20261023` |  | obsolete: 225/362 commits conflict with rewritten main; the 6 clean picks are 1-line "complete" seam markers and a CI trigger for a dead branch (stubs) |
| `recovery/dirty91-skeleton-media-lafs-deepen-20261107-200415-56b1fe` |  | needs-work: media_depth ported locally but 141/345 tests fail against main MediaStudio API; not published |
| `reconcile/backup-pr-4551-e559e56963b68703939848b2da300003d4680b51` | 0 clean / 1 conflicting / 0 empty / 0 patch-id on main | pending: all unique commits conflict (dirty-snapshot); file-level port needed |
| `reconcile/consumer-compose-private-published-regression-20261108-r02` | 1 clean / 4 conflicting / 4 empty / 0 patch-id on main | pending triage: needs manual conflict resolution |
| `reconcile/draft-promotion-source-convergence-20261108-r03` | 23 clean / 43 conflicting / 12 empty / 0 patch-id on main | pending triage: needs manual conflict resolution |
| `reconcile/jeeves-world-player-save-keyboard-20261108-r01` | 2 clean / 1 conflicting / 0 empty / 0 patch-id on main | pending triage: needs manual conflict resolution |
| `reconcile/source-convergence-exact-head-qualification-20261108-r01` | 6 clean / 28 conflicting / 9 empty / 0 patch-id on main | pending triage: needs manual conflict resolution |
| `recovery/dirty102-code-state-skeleton-f4-20261107-202211-50b11f` | 0 clean / 1 conflicting / 0 empty / 0 patch-id on main | pending: all unique commits conflict (dirty-snapshot); file-level port needed |
| `recovery/dirty102-code-state-skeleton-outbox-20261107-202211-9bc509` | 0 clean / 1 conflicting / 0 empty / 0 patch-id on main | pending: all unique commits conflict (dirty-snapshot); file-level port needed |
| `recovery/dirty102-code-state-skeleton-willy-b025-20261107-202229-e1a357` | 1 clean / 1 conflicting / 0 empty / 0 patch-id on main | pending triage: needs manual conflict resolution |
| `recovery/dirty102-deletion-heavy-state-[redacted-key-shaped-branch-suffix]` | 0 clean / 1 conflicting / 0 empty / 0 patch-id on main | pending: all unique commits conflict (dirty-snapshot); file-level port needed |
| `recovery/dirty102-deletion-heavy-state-skeleton-cos-export-20261107-202325-636db1` | 0 clean / 1 conflicting / 0 empty / 0 patch-id on main | pending: all unique commits conflict (dirty-snapshot); file-level port needed |
| `recovery/pr5097-pre-rebase-20261110` | 4 clean / 14 conflicting / 6 empty / 0 patch-id on main | pending triage: needs manual conflict resolution |
| `recovery/pre-rebase-jeeves-native-r88-20261113-r2` | 4 clean / 191 conflicting / 107 empty / 0 patch-id on main | pending triage: needs manual conflict resolution |
| `reconcile/first-install-security-convergence-20261108-b05` | 45 clean / 144 conflicting / 55 empty / 0 patch-id on main | pending triage: needs manual conflict resolution |
| `reconcile/full-repo-audit-manual-bounded-20261108-r01` | 0 clean / 5 conflicting / 1 empty / 0 patch-id on main | pending: all unique commits conflict (dirty-snapshot); file-level port needed |
| `reconcile/jeeves-world-player-source-custody-20261108-r01` | 2 clean / 2 conflicting / 0 empty / 0 patch-id on main | pending triage: needs manual conflict resolution |
| `reconcile/quarantine-api-v1-edge-20261108-r1` | 1 clean / 14 conflicting / 5 empty / 0 patch-id on main | pending triage: needs manual conflict resolution |
| `reconcile/strict-compose-loopback-full-service-audit-20261108-r01` | 0 clean / 3 conflicting / 1 empty / 0 patch-id on main | pending: all unique commits conflict (dirty-snapshot); file-level port needed |
| `recovery/dirty102-code-state-skeleton-willy-gfc-20261107-202223-1cece7` | 0 clean / 1 conflicting / 0 empty / 0 patch-id on main | pending: all unique commits conflict (dirty-snapshot); file-level port needed |
| `recovery/dirty102-deletion-heavy-state-skeleton-bork-20261107-202315-ede329` | 0 clean / 1 conflicting / 0 empty / 0 patch-id on main | pending: all unique commits conflict (dirty-snapshot); file-level port needed |
| `recovery/dirty102-deletion-heavy-state-skeleton-cos-export-20261107-202951-c17b48` | 0 clean / 1 conflicting / 0 empty / 0 patch-id on main | pending: all unique commits conflict (dirty-snapshot); file-level port needed |
| `recovery/dirty102-deletion-heavy-state-skeleton-github-ops-20261107-202324-a7a5d2` | 0 clean / 1 conflicting / 0 empty / 0 patch-id on main | pending: all unique commits conflict (dirty-snapshot); file-level port needed |
| `recovery/pr5064-pre-rebase-20261110` | 43 clean / 133 conflicting / 52 empty / 0 patch-id on main | pending triage: needs manual conflict resolution |
| `recovery/pre-rebase-game-frontier-20261113-r2` | 0 clean / 249 conflicting / 125 empty / 0 patch-id on main | pending: all unique commits conflict (dirty-snapshot); file-level port needed |
| `recovery/pre-rebase-jeeves-native-r89-20261113-r2` | 4 clean / 191 conflicting / 107 empty / 0 patch-id on main | pending triage: needs manual conflict resolution |
| `reconcile/draft19-studio-archive-inspection-20261108-r01` | 7 clean / 27 conflicting / 11 empty / 0 patch-id on main | pending triage: needs manual conflict resolution |
| `reconcile/jeeves-browser-save-20261109-r05` | 5 clean / 5 conflicting / 6 empty / 0 patch-id on main | pending triage: needs manual conflict resolution |
| `reconcile/native-profile-strict-evidence-20261108-r01` | 1 clean / 2 conflicting / 0 empty / 0 patch-id on main | pending triage: needs manual conflict resolution |
| `recovery/dirty102-code-state-is-guard-20261107-202211-df7e78` | 0 clean / 2 conflicting / 1 empty / 0 patch-id on main | pending: all unique commits conflict (dirty-snapshot); file-level port needed |
| `recovery/dirty102-code-state-skeleton-20261107-202210-bda12a` | 0 clean / 1 conflicting / 0 empty / 0 patch-id on main | pending: all unique commits conflict (dirty-snapshot); file-level port needed |
| `recovery/dirty102-code-state-skeleton-olly-pack-j-20261107-202241-d637f0` | 0 clean / 1 conflicting / 0 empty / 0 patch-id on main | pending: all unique commits conflict (dirty-snapshot); file-level port needed |
| `recovery/dirty102-code-state-skeleton-roger-20261107-202322-fa2bab` | 0 clean / 1 conflicting / 0 empty / 0 patch-id on main | pending: all unique commits conflict (dirty-snapshot); file-level port needed |
| `recovery/dirty102-deletion-heavy-state-skeleton-char-polish-api-20261107-202333-eb0ed3` | 0 clean / 1 conflicting / 0 empty / 0 patch-id on main | pending: all unique commits conflict (dirty-snapshot); file-level port needed |
| `recovery/dirty102-deletion-heavy-state-skeleton-cos-forge2-20261107-202257-9e823f` | 0 clean / 1 conflicting / 0 empty / 0 patch-id on main | pending: all unique commits conflict (dirty-snapshot); file-level port needed |
| `recovery/dirty102-deletion-heavy-state-skeleton-glenny-20261107-202322-ae8b55` | 0 clean / 1 conflicting / 0 empty / 0 patch-id on main | pending: all unique commits conflict (dirty-snapshot); file-level port needed |
| `recovery/dirty102-deletion-heavy-state-skeleton-willy-20261107-202323-0b4371` | 0 clean / 1 conflicting / 0 empty / 0 patch-id on main | pending: all unique commits conflict (dirty-snapshot); file-level port needed |
| `recovery/pr5017-pre-rebase-20261110` | 43 clean / 134 conflicting / 49 empty / 1 patch-id on main | pending triage: needs manual conflict resolution |
| `reconcile/backup-pr-4685-2551aa149d5908a661b3a3a9ca2307aa5dfcd217` | 0 clean / 25 conflicting / 10 empty / 0 patch-id on main | pending: all unique commits conflict (dirty-snapshot); file-level port needed |
| `reconcile/consumer-compose-loopback-tests-20261108-r01` | 0 clean / 2 conflicting / 1 empty / 0 patch-id on main | pending: all unique commits conflict (dirty-snapshot); file-level port needed |
| `reconcile/jeeves-world-custody-mirror-20261109-r02` | 0 clean / 3 conflicting / 5 empty / 0 patch-id on main | pending: all unique commits conflict (dirty-snapshot); file-level port needed |
| `reconcile/p0-mass-dragon-volumes-20261108-r01` | 3 clean / 16 conflicting / 6 empty / 0 patch-id on main | pending triage: needs manual conflict resolution |
| `reconcile/quarantine-ecs-agent-ai-20261108-r1` | 0 clean / 7 conflicting / 1 empty / 0 patch-id on main | pending: all unique commits conflict (dirty-snapshot); file-level port needed |
| `recovery/dirty102-code-state-[redacted-key-shaped-branch-suffix]` | 1 clean / 0 conflicting / 0 empty / 0 patch-id on main | pending: clean, not yet published |
| `recovery/dirty102-code-state-skeleton-f3-20261107-202210-7e0632` | 0 clean / 1 conflicting / 0 empty / 0 patch-id on main | pending: all unique commits conflict (dirty-snapshot); file-level port needed |
| `recovery/dirty102-code-state-wt-4253-20261107-202213-35fcc9` | 0 clean / 1 conflicting / 0 empty / 0 patch-id on main | pending: all unique commits conflict (dirty-snapshot); file-level port needed |
| `recovery/dirty102-deletion-heavy-state-skeleton-cos-b023-20261107-202325-101d2a` | 0 clean / 1 conflicting / 0 empty / 0 patch-id on main | pending: all unique commits conflict (dirty-snapshot); file-level port needed |
| `recovery/dirty102-deletion-heavy-state-skeleton-cos-land-20261107-202324-154f50` | 0 clean / 1 conflicting / 0 empty / 0 patch-id on main | pending: all unique commits conflict (dirty-snapshot); file-level port needed |
| `recovery/dirty102-deletion-heavy-state-skeleton-gronk-20261107-202312-66fa62` | 0 clean / 1 conflicting / 0 empty / 0 patch-id on main | pending: all unique commits conflict (dirty-snapshot); file-level port needed |
| `recovery/dirty91-gl-jv-20261107-192241-644d7c` | 1 clean / 0 conflicting / 0 empty / 0 patch-id on main | pending: clean, not yet published |
| `recovery/pre-rebase-jeeves-native-r87-20261113-r2` | 4 clean / 190 conflicting / 107 empty / 0 patch-id on main | pending triage: needs manual conflict resolution |
