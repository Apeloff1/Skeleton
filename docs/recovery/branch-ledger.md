# Historic, archive and recovery branch ledger

Generated 2026-11-22 01:41 CET by Lane D against `main` at `881c918d74`. It covers every remote branch except `main` (1948 branches).

Each branch gets one status:

- **fully on main**: every additive change is already on main, byte for byte or at a relocated path, or merging it onto main changes nothing once deletions are ignored.
- **ported in PR #X**: its unique additive content was ported onto a fresh branch from current main in that PR.
- **nothing unique**: its remaining changes are older edits that conflict with newer versions on main, deletion-dominant snapshots, or generated mass scaffolding. Deletions are never ported.
- **unique content pending port**: additive content survives a 3-way merge onto main and has not been ported yet. This is the work queue.

## Method
1. `git merge-tree --write-tree main <tip>`, then `git diff main <merged-tree>`. Only added or modified paths outside conflict hunks count, and deletions are ignored.
2. Added files are compared by content: line overlap of at least 90% with a same-named file on main counts as relocated.
3. Snapshot branches without a shared history (the `recovery/dirty102-*` and `dirty91-*` states) are compared blob by blob against the main tree. The 2026-11-14 backend audit verdicts are reused where they exist.

## Summary

| status | branches |
|---|---|
| nothing unique | 731 |
| fully on main | 534 |
| unique content pending port | 493 |
| ported in PR #5767 | 160 |
| ported in PR #5771 | 16 |
| not analysed | 8 |
| ported in PR #5779 | 6 |

## Ledger

| branch | tip | date | status | note |
|---|---|---|---|---|
| `archive/ai-startup-4205-pre-reconcile-20261023` | `2405c2be34` | 2026-10-23 | nothing unique | superseded: its 47 remaining edits conflict with newer main versions |
| `archive/ai-startup-4205-pre-secret-reconcile-20261023` | `55e4f8bbdd` | 2026-10-23 | nothing unique | superseded: its 28 remaining edits conflict with newer main versions |
| `archive/forge-postepoch-4202-pre-reconcile-20261023` | `692d0f0d0e` | 2026-10-23 | unique content pending port | 14 new files, 0 modified files survive a 3-way merge; e.g. docs/ABSOLUTE_4202.md, docs/FINAL_4202.md, docs/GIGA_ULTRA_4202.md |
| `archive/frontier-m14-integrity-pre-rebase-20261023` | `e19791b4cc` | 2026-10-23 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `archive/frontier-milestone-14-pre-reconcile-20261023` | `6fd4a56493` | 2026-10-22 | nothing unique | generated mass scaffolding (600k+ templated files) / generated docs; not product content |
| `archive/pre-rebase-807-b028-20261113-130d7927` | `130d792744` | 2026-10-24 | fully on main | every changed blob already on main |
| `archive/pre-rebase-807-b028-20261114-20b0ab6e` | `20b0ab6e2f` | 2026-11-13 | fully on main | every changed blob already on main |
| `archive/pre-rebase-807-b030-20261113-5b072c04` | `5b072c04d9` | 2026-10-24 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `archive/pre-rebase-807-b030-20261114-f314ef19` | `f314ef1958` | 2026-11-13 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `archive/pre-rebase-807-b037-20261113-ff9b6c2b` | `ff9b6c2bf6` | 2026-10-24 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `archive/pre-rebase-807-b037-20261114-8f5fc6b8` | `8f5fc6b896` | 2026-11-13 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `archive/pre-rebase-807-net-w1-20261113-d2cde7bb` | `d2cde7bb27` | 2026-10-25 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `archive/pre-rebase-807-world-backend-20261113-872d445b` | `872d445b33` | 2026-11-05 | fully on main | every changed blob already on main |
| `archive/pre-rebase-admission-lease-20261113-e3b4f277` | `e3b4f2777f` | 2026-11-13 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `archive/pre-rebase-adventure-systems-depth-20261113-f9042d52` | `f9042d5288` | 2026-10-15 | fully on main | every changed blob already on main |
| `archive/pre-rebase-art-acceptance-20261113-1db4e2b5` | `1db4e2b59c` | 2026-10-24 | fully on main | every changed blob already on main |
| `archive/pre-rebase-asset-ingest-20261113-3d153f38` | `3d153f3858` | 2026-11-05 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `archive/pre-rebase-choice-ledger-20261113-268d121e` | `268d121e36` | 2026-11-05 | fully on main | every changed blob already on main |
| `archive/pre-rebase-ci-jeeves-contracts-glenny-20261031-20261113-bed41435` | `bed41435ce` | 2026-10-31 | fully on main | every changed blob already on main |
| `archive/pre-rebase-client-projects-20261113-296328f4` | `296328f44d` | 2026-10-17 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `archive/pre-rebase-client-realtime-wire-20261113-5be6fa44` | `5be6fa44f5` | 2026-10-18 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `archive/pre-rebase-design-bible-asset-depth-20261113-5bd6acc8` | `5bd6acc8af` | 2026-10-15 | fully on main | every changed blob already on main |
| `archive/pre-rebase-devops-perf-budgets-json-limit-20261113-c8878e31` | `c8878e3125` | 2026-10-17 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `archive/pre-rebase-fixed-tick-clock-20261113-aefb787d` | `aefb787df4` | 2026-11-09 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `archive/pre-rebase-frontier-chunk-telemetry-20261113-fbe19010` | `fbe19010e8` | 2026-10-31 | fully on main | every changed blob already on main |
| `archive/pre-rebase-frontier-milestone-14-20261113-67f6e808` | `67f6e808fc` | 2026-10-23 | fully on main | every changed blob already on main |
| `archive/pre-rebase-frontier-milestone-9-20261113-aafae5c1` | `aafae5c12e` | 2026-10-20 | fully on main | every changed blob already on main |
| `archive/pre-rebase-full-lens-review-20261113-827db0de` | `827db0de8b` | 2026-10-17 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `archive/pre-rebase-gameforge-b039-20261113-61ec9b8a` | `61ec9b8abc` | 2026-10-31 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `archive/pre-rebase-gameforge-conductor-20261113-8e20778a` | `8e20778a4b` | 2026-10-24 | fully on main | every changed blob already on main |
| `archive/pre-rebase-gf-b020-char-20261113-2c43b3dc` | `2c43b3dced` | 2026-10-24 | fully on main | every changed blob already on main |
| `archive/pre-rebase-gf-b023-script-runtime-20261113-9e45335e` | `9e45335e0d` | 2026-10-31 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `archive/pre-rebase-gf-b024-input-actions-20261113-80e57ea7` | `80e57ea7d5` | 2026-10-31 | nothing unique | superseded: its 5 remaining edits conflict with newer main versions |
| `archive/pre-rebase-gf-b038-oyvind-20261024-20261113-0aa82739` | `0aa8273938` | 2026-10-25 | fully on main | every changed blob already on main |
| `archive/pre-rebase-gf-b040-carrol-20261113-9b6cd0a3` | `9b6cd0a342` | 2026-10-24 | fully on main | every changed blob already on main |
| `archive/pre-rebase-gf-b040-coderlead-20261113-c9d8820e` | `c9d8820e33` | 2026-10-24 | fully on main | every changed blob already on main |
| `archive/pre-rebase-gf-b040-s4s5-20261113-c6a5a6c7` | `c6a5a6c771` | 2026-10-24 | fully on main | every changed blob already on main |
| `archive/pre-rebase-gf-build-evidence-20261113-7494dc06` | `7494dc06b5` | 2026-10-25 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `archive/pre-rebase-gf-d-20261113-74bd2f71` | `74bd2f7119` | 2026-10-25 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `archive/pre-rebase-gf-f-char-20261113-fa867b1d` | `fa867b1d16` | 2026-10-25 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `archive/pre-rebase-gf-h-nav-20261113-d1de13ac` | `d1de13ac3a` | 2026-10-25 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `archive/pre-rebase-gf-j-location-20261113-f9cb4408` | `f9cb44081c` | 2026-10-26 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `archive/pre-rebase-gguf-preflight-20261113-217e7e33` | `217e7e3363` | 2026-11-09 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `archive/pre-rebase-grid-goal-20261113-a6cc0f2e` | `a6cc0f2e92` | 2026-11-09 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `archive/pre-rebase-input-collision-20261113-8a758fc7` | `8a758fc7e0` | 2026-11-09 | fully on main | every changed blob already on main |
| `archive/pre-rebase-jeeves-dragon-e2e-20261113-79163fb4` | `79163fb4d0` | 2026-10-17 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `archive/pre-rebase-kv-pressure-20261113-cd896e58` | `cd896e5895` | 2026-11-05 | fully on main | every changed blob already on main |
| `archive/pre-rebase-mb-api-docs-jenkins-20261031-20261113-244cae4a` | `244cae4a83` | 2026-11-05 | fully on main | every changed blob already on main |
| `archive/pre-rebase-mb-arch-docs-20261113-315bc99e` | `315bc99e8c` | 2026-11-05 | fully on main | every changed blob already on main |
| `archive/pre-rebase-mb-b031-b040-20261113-c224b009` | `c224b009e9` | 2026-11-05 | fully on main | every changed blob already on main |
| `archive/pre-rebase-mb-gf-l-20261113-0fa65b10` | `0fa65b100a` | 2026-11-05 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `archive/pre-rebase-mb-gf-l-route-repair-20261114-98dc22f` | `98dc22f996` | 2026-11-13 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `archive/pre-rebase-mb-gfa-20261113-ce1bf3c1` | `ce1bf3c1f2` | 2026-11-05 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `archive/pre-rebase-mb-perf-profiler-20261113-9b0124c1` | `9b0124c171` | 2026-11-05 | nothing unique | superseded: its 13 remaining edits conflict with newer main versions |
| `archive/pre-rebase-mb-player-analytics-oyvind-20261031-20261113-cc1436d9` | `cc1436d93d` | 2026-11-05 | fully on main | every changed blob already on main |
| `archive/pre-rebase-mb-project-bundle-20261113-eb310c4f` | `eb310c4f83` | 2026-10-31 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `archive/pre-rebase-mb-quest-system-oyvind-20261031-20261113-f376e95f` | `f376e95f1d` | 2026-11-05 | fully on main | every changed blob already on main |
| `archive/pre-rebase-nvml-probe-20261113-d4aed6ef` | `d4aed6ef45` | 2026-10-31 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `archive/pre-rebase-offline-cpu-budget-20261113-014ea61e` | `014ea61ead` | 2026-11-05 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `archive/pre-rebase-production-planning-depth-20261113-332c58cf` | `332c58cf20` | 2026-10-15 | fully on main | every changed blob already on main |
| `archive/pre-rebase-quiz-bank-20261113-a7a5f3aa` | `a7a5f3aaa9` | 2026-10-31 | fully on main | every changed blob already on main |
| `archive/pre-rebase-scene-byte-boundary-20261113-90ebe39c` | `90ebe39c08` | 2026-11-08 | fully on main | every changed blob already on main |
| `archive/pre-rebase-scene-graph-depth-20261113-62dd0eac` | `62dd0eacb8` | 2026-11-08 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `archive/pre-rebase-shard-seal-20261113-bc94479a` | `bc94479a12` | 2026-10-24 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `archive/pre-rebase-studio-b-godot-custody-20261113-c0576fcb` | `c0576fcb82` | 2026-11-09 | fully on main | every changed blob already on main |
| `archive/pre-rebase-studio-b-grid-input-adapter-20261113-345a996a` | `345a996a5c` | 2026-11-09 | fully on main | every changed blob already on main |
| `archive/pre-rebase-studio-c-cpu-kv-durable-spill-20261031-r06-20261113-efadcdc3` | `efadcdc327` | 2026-11-05 | fully on main | every changed blob already on main |
| `archive/pre-rebase-studio-c-pressure-aware-iteration-schedule-20261113-0d6c6716` | `0d6c6716e9` | 2026-11-05 | fully on main | every changed blob already on main |
| `archive/pre-rebase-telemetry-121-20261113-dbb23f65` | `dbb23f65d3` | 2026-10-24 | fully on main | every changed blob already on main |
| `archive/pre-rebase-weight-inventory-20261113-dfab6583` | `dfab658391` | 2026-11-05 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `archive/pre-rebase-world-identity-fence-20261113-ac86c688` | `ac86c68839` | 2026-11-09 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `asset-custody/emerald-20261117-r1-lfs` | `d82d61541b` | 2026-11-17 | unique content pending port | 63 new files, 14 modified files survive a 3-way merge; 1 paths already carried by port PRs; e.g. .github/workflows/dragon-atelier-prototype.yml, artifacts/emerald/.gitignore, artifacts/emerald/original-r1/.gitattributes |
| `assets/emerald-original-model-a-20261117` | `ceb09cacce` | 2026-11-17 | unique content pending port | 69 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5535 (mergeable) -> feat/emerald-binary-publication-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-original-publication.yml, artifacts/emerald/.gitignore |
| `assets/emerald-original-model-b-20261117` | `eae27c15fd` | 2026-11-17 | unique content pending port | 69 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5536 (mergeable) -> feat/emerald-binary-publication-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-original-publication.yml, artifacts/emerald/.gitignore |
| `assets/emerald-original-model-c-20261117` | `2b581a0ace` | 2026-11-17 | unique content pending port | 69 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5537 (mergeable) -> feat/emerald-binary-publication-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-original-publication.yml, artifacts/emerald/.gitignore |
| `assets/emerald-original-source-20261117` | `f56c77bead` | 2026-11-17 | unique content pending port | 69 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5534 (mergeable) -> feat/emerald-binary-publication-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-original-publication.yml, artifacts/emerald/.gitignore |
| `assets/emerald-original-web-20261117` | `032ccb9763` | 2026-11-17 | unique content pending port | 69 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5533 (mergeable) -> feat/emerald-binary-publication-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-original-publication.yml, artifacts/emerald/.gitignore |
| `assets/emerald-poster-v4-archivist-20261117` | `0bec2c09d7` | 2026-11-17 | unique content pending port | 81 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5555 (mergeable) -> feat/emerald-poster-v4-anatomical-custody-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `assets/emerald-poster-v4-hatchling-20261117` | `8c7ddf4056` | 2026-11-17 | unique content pending port | 81 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5551 (mergeable) -> feat/emerald-poster-v4-anatomical-custody-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `assets/emerald-poster-v4-pathfinder-20261117` | `23426f2b70` | 2026-11-17 | unique content pending port | 81 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5554 (mergeable) -> feat/emerald-poster-v4-anatomical-custody-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `assets/emerald-poster-v4-scholar-20261117` | `5949eaa26e` | 2026-11-17 | unique content pending port | 81 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5553 (mergeable) -> feat/emerald-poster-v4-anatomical-custody-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `assets/emerald-poster-v4-scout-20261117` | `e9d6d066c1` | 2026-11-17 | unique content pending port | 81 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5552 (mergeable) -> feat/emerald-poster-v4-anatomical-custody-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `assets/emerald-v5-archivist-proximal-20261117` | `f2ddb01ebf` | 2026-11-17 | unique content pending port | 108 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5567 (mergeable) -> feat/emerald-v5-proximal-wingfold-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `assets/emerald-v5-pathfinder-proximal-20261117` | `db5ad19cab` | 2026-11-17 | unique content pending port | 108 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5566 (mergeable) -> feat/emerald-v5-proximal-wingfold-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `assets/emerald-v5-scholar-wingfold-r1-20261117` | `a30b090e2d` | 2026-11-17 | unique content pending port | 99 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5564 (mergeable) -> feat/emerald-v5-scholar-wingfold-custody-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `assets/emerald-v6-archivist-tail-clearance-20261117` | `0e27ba5c2e` | 2026-11-17 | unique content pending port | 131 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5572 (mergeable) -> feat/emerald-v6-exact-binary-transport-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `assets/emerald-v6-pathfinder-tail-clearance-20261117` | `c6ff51c05a` | 2026-11-17 | unique content pending port | 131 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5571 (mergeable) -> feat/emerald-v6-exact-binary-transport-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `assets/emerald-v7-archivist-orbit02-20261117` | `3ab0150079` | 2026-11-17 | unique content pending port | 152 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5580 (mergeable) -> feat/emerald-v7-binary-custody-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `assets/emerald-v7-pathfinder-orbit02-20261117` | `ca8e23125a` | 2026-11-17 | unique content pending port | 152 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5579 (mergeable) -> feat/emerald-v7-binary-custody-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `assets/emerald-weighted-v3-archivist-20261117` | `c5595da954` | 2026-11-17 | unique content pending port | 80 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5548 (mergeable) -> feat/emerald-v3-draft-publication-custody-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-weighted-publication.yml |
| `assets/emerald-weighted-v3-hatchling-20261117` | `00d43b04c8` | 2026-11-17 | unique content pending port | 80 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5544 (mergeable) -> feat/emerald-v3-draft-publication-custody-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-weighted-publication.yml |
| `assets/emerald-weighted-v3-pathfinder-20261117` | `47fa36d8af` | 2026-11-17 | unique content pending port | 80 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5547 (mergeable) -> feat/emerald-v3-draft-publication-custody-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-weighted-publication.yml |
| `assets/emerald-weighted-v3-scholar-20261117` | `86b4b8a433` | 2026-11-17 | unique content pending port | 80 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5546 (mergeable) -> feat/emerald-v3-draft-publication-custody-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-weighted-publication.yml |
| `assets/emerald-weighted-v3-scout-20261117` | `9525ba1032` | 2026-11-17 | unique content pending port | 80 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5545 (mergeable) -> feat/emerald-v3-draft-publication-custody-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-weighted-publication.yml |
| `audit/codex-vm-exact-parity-20261024` | `ea4fa84d63` | 2026-10-25 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `audit/codex-vm-source-parity-20261024` | `6ebc2b6102` | 2026-10-24 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `audit/full-repo-sweep-20261106` | `de17c38272` | 2026-11-06 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `audit/full-repository-sweep-20261106` | `cdd971b312` | 2026-11-06 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. .github/workflows/full-repository-sweep-20261106.yml |
| `audit/post-merge-integration-20261110-r01` | `70513dd24f` | 2026-11-10 | fully on main | every changed blob already on main |
| `automation/conveyor-first-run-inode-fixture-20261108` | `7a4482d37e` | 2026-11-09 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `automation/repo-navigation-index` | `fcb894d833` | 2026-10-16 | unique content pending port | 2 new files, 65 modified files survive a 3-way merge; e.g. machine/repo_navigation/feature_routes/data.json, machine/repo_navigation/files/data.jsonl |
| `automation/studio-a-v6-unicode-ingress-20261108-1801` | `7e212c36a4` | 2026-11-09 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `automation/studio-b-v6-empty-certification-failclosed-20261108-1416` | `2b65fd80ee` | 2026-11-08 | fully on main | every changed blob already on main |
| `automation/studio-d-health-probe-validation-20261108` | `5730726e39` | 2026-11-08 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `automation/v6-b-fixed-tick-20261109-1016` | `8b5b1eb9dc` | 2026-11-09 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `automation/v6-c-20261108-operational-inference-truth` | `dd469fc5af` | 2026-11-08 | fully on main | every changed blob already on main |
| `automation/v6d-health-url-admission-20261109-09` | `0c52465a93` | 2026-11-09 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `automation/v6d-probe-response-failclosed-20261109-11` | `a76b481e8d` | 2026-11-09 | fully on main | every changed blob already on main |
| `cherry-recovery` | `012155e296` | 2026-11-14 | fully on main | every changed blob already on main |
| `chore/branch-content-coverage-20261016` | `4acbd5afdd` | 2026-10-16 | fully on main | every changed blob already on main |
| `chore/draft-forms-flgb-100-reconciliation-20261016` | `fe88395f94` | 2026-10-16 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `chore/flgb-static-depth-reconciliation-20261016` | `77e975b711` | 2026-10-16 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `ci/emerald-v7-consolidated-exact-head-source-20261118` | `6bd825efe4` | 2026-11-18 | unique content pending port | 211 new files, 12 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5604 (mergeable) -> feat/emerald-v7-two-model-evidence-revalidation-20261118; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `ci/gf-d-native-smoke-20261024` | `a852ba2530` | 2026-10-24 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `ci/jeeves-gguf-sqlite-full-assurance-20261104-r43` | `a0aa1354f8` | 2026-11-05 | nothing unique | superseded: its 145 remaining edits conflict with newer main versions |
| `ci/jeeves-native-sqlite-first-laptop-source-qualification-20261104-r15` | `b16f79111e` | 2026-11-05 | nothing unique | superseded: its 175 remaining edits conflict with newer main versions |
| `ci/main-ci-queue-20261024` | `462cdab42e` | 2026-10-25 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `clean-extract-5285-game-builder` | `881c918d74` | 2026-11-19 | fully on main | 0 commits ahead |
| `clean-extract-5300-gameforge` | `881c918d74` | 2026-11-19 | fully on main | 0 commits ahead |
| `clean-extract-5315-gameforge` | `881c918d74` | 2026-11-19 | fully on main | 0 commits ahead |
| `clean-extract-5349-ci` | `881c918d74` | 2026-11-19 | fully on main | 0 commits ahead |
| `clean-extract-5350-telemetry` | `881c918d74` | 2026-11-19 | fully on main | 0 commits ahead |
| `clean-extract-5353-telemetry` | `881c918d74` | 2026-11-19 | fully on main | 0 commits ahead |
| `clean-extract-5369-reconcile` | `881c918d74` | 2026-11-19 | fully on main | 0 commits ahead |
| `clean-extract-5370-jeeves` | `881c918d74` | 2026-11-19 | fully on main | 0 commits ahead |
| `clean-extract-5373-jeeves` | `881c918d74` | 2026-11-19 | fully on main | 0 commits ahead |
| `clean-extract-5376-jeeves` | `881c918d74` | 2026-11-19 | fully on main | 0 commits ahead |
| `clean-extract-5398-gameforge` | `881c918d74` | 2026-11-19 | fully on main | 0 commits ahead |
| `clean-extract-5400-studio-c` | `881c918d74` | 2026-11-19 | fully on main | 0 commits ahead |
| `clean-extract-5404-reconcile` | `881c918d74` | 2026-11-19 | fully on main | 0 commits ahead |
| `clean-extract-5405-integration` | `881c918d74` | 2026-11-19 | fully on main | 0 commits ahead |
| `clean-extract-5415-machine` | `881c918d74` | 2026-11-19 | fully on main | 0 commits ahead |
| `clean-extract-5419-ci` | `881c918d74` | 2026-11-19 | fully on main | 0 commits ahead |
| `clean-extract-5421-security` | `881c918d74` | 2026-11-19 | fully on main | 0 commits ahead |
| `clean-extract-5422-integration` | `881c918d74` | 2026-11-19 | fully on main | 0 commits ahead |
| `clean-extract-5429-dragon` | `881c918d74` | 2026-11-19 | fully on main | 0 commits ahead |
| `clean-extract-5464-jeeves` | `881c918d74` | 2026-11-19 | fully on main | 0 commits ahead |
| `clean-extract-5465-jeeves` | `881c918d74` | 2026-11-19 | fully on main | 0 commits ahead |
| `clean-extract-5469-jeeves-chat` | `881c918d74` | 2026-11-19 | fully on main | 0 commits ahead |
| `clean-extract-5474-hyperdispatcher` | `881c918d74` | 2026-11-19 | fully on main | 0 commits ahead |
| `clean-extract-5479-first-install` | `881c918d74` | 2026-11-19 | fully on main | 0 commits ahead |
| `clean-extract-5485-ci` | `881c918d74` | 2026-11-19 | fully on main | 0 commits ahead |
| `clean-extract-5487-offline` | `881c918d74` | 2026-11-19 | fully on main | 0 commits ahead |
| `clean-extract-5491-native` | `881c918d74` | 2026-11-19 | fully on main | 0 commits ahead |
| `clean-extract-5499-emerald` | `7f61338635` | 2026-11-19 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. docs/EMERALD_OFFLINE_ASSETS.md |
| `clean-extract-5629-local` | `881c918d74` | 2026-11-19 | fully on main | 0 commits ahead |
| `clean-extract-5642-stubs` | `881c918d74` | 2026-11-19 | fully on main | 0 commits ahead |
| `codex/adaptive-ai-runtime-2026-10-20` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `codex/ai-studio-foundations-2026-10-20` | `e6a17b5caf` | 2026-10-23 | nothing unique | superseded: its 29 remaining edits conflict with newer main versions |
| `codex/consumer-preinstall-2026-10-31` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `codex/consumer-runtime-readiness-2026-10-25` | `71a609644a` | 2026-10-29 | unique content pending port | 0 new files, 3 modified files survive a 3-way merge |
| `codex/jeeves-original-studio-completion-2026-10-15` | `305c8a89b8` | 2026-10-15 | unique content pending port | 1 new files, 1 modified files survive a 3-way merge; e.g. frontend/features/Setup/AppSetupWorkspace.tsx |
| `codex/merge-first-install-2026-10-15` | `0bf596c78e` | 2026-10-15 | unique content pending port | 0 new files, 5 modified files survive a 3-way merge |
| `conveyor/v6-fix-main-syntax-gates-20261108` | `29307d3e3e` | 2026-11-08 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `cos/factory-brief-20261024` | `77c0de258d` | 2026-10-25 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `cursor/architecture-boundaries-d604` | `879c3dd2ef` | 2026-10-18 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `cursor/authoritative-fixed-step-runtime-dfa0` | `367b062614` | 2026-11-19 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge; 10 paths already carried by port PRs |
| `cursor/boot-route-and-projection-62a2` | `c388105322` | 2026-10-18 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `cursor/ci-lane-dedupe-3ec3` | `e7c25b2e5b` | 2026-10-18 | nothing unique | superseded: its 22 remaining edits conflict with newer main versions |
| `cursor/claim-faithfulness-gate-9a51` | `d22c2dab74` | 2026-10-17 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `cursor/claim-verification-completion-c457` | `af7c877fd5` | 2026-11-19 | unique content pending port | 3 new files, 14 modified files survive a 3-way merge; open PR #5630 (mergeable) -> cursor/local-reviewed-turn-b4af; e.g. skeleton/app/local_reviewed_turn.py, skeleton/testing/test_admission_completion_reconciliation.py, skeleton/testing/test_local_reviewed_turn.py |
| `cursor/complete-local-tool-stubs-f405` | `84370484b8` | 2026-11-19 | unique content pending port | 7 new files, 7 modified files survive a 3-way merge; e.g. skeleton/local_ai/desk_journal.py, skeleton/local_ai/desk_model.py, skeleton/local_ai/memory_book.py |
| `cursor/connect-orphan-surfaces-e83e` | `8b3ef4653a` | 2026-11-19 | unique content pending port | 7 new files, 25 modified files survive a 3-way merge; 1 paths already carried by port PRs; e.g. frontend/app/surfaces.tsx, frontend/src/product/surfaceAtlas.ts, scripts/generate_surface_atlas.py |
| `cursor/cutting-edge-train-11d5` | `74509974f2` | 2026-10-18 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `cursor/dragon-companion-upscale-4d0c` | `eceb7014f9` | 2026-10-17 | nothing unique | superseded: its 6 remaining edits conflict with newer main versions |
| `cursor/english-game-pareto-11d5` | `476ab2d830` | 2026-10-18 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `cursor/forge-plan-era-a11y-7487` | `bd66c58f87` | 2026-10-17 | nothing unique | superseded: its 7 remaining edits conflict with newer main versions |
| `cursor/game-builder-pipeline-572d` | `7c3fadea5a` | 2026-10-17 | nothing unique | superseded: its 21 remaining edits conflict with newer main versions |
| `cursor/game-longform-completion-572d` | `4314220a11` | 2026-10-17 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `cursor/game-scale-argon-11d5` | `2bd285afd9` | 2026-10-18 | fully on main | every changed blob already on main |
| `cursor/game-studio-swarm-eff0` | `4a933afc19` | 2026-10-17 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `cursor/game-visual-billion-11d5` | `d36e651002` | 2026-11-19 | fully on main | every changed blob already on main |
| `cursor/gapfill-service-identity-6f14` | `7090e9c6ac` | 2026-10-17 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `cursor/gapfill-trust-root-recovery-6f14` | `ddf8201c88` | 2026-10-17 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `cursor/jeeves-adaptive-reactive-weights-8dc4` | `5628735df0` | 2026-11-19 | unique content pending port | 7 new files, 4 modified files survive a 3-way merge; e.g. skeleton/ai/runtime/cortex/dynamic_weights.py, skeleton/ai/runtime/cortex/weight_pretrain.py, skeleton/cortex/dynamic_weights.py |
| `cursor/jeeves-claim-faithfulness-32d9` | `24bc17c6da` | 2026-11-19 | unique content pending port | 1 new files, 6 modified files survive a 3-way merge; e.g. skeleton/intelligence/neural_faithfulness.py |
| `cursor/local-desk-model-gapfill-f405` | `caec0845f4` | 2026-11-19 | unique content pending port | 7 new files, 7 modified files survive a 3-way merge; open PR #5643 (mergeable) -> cursor/local-tool-stub-gapfill-f405; e.g. skeleton/local_ai/desk_journal.py, skeleton/local_ai/desk_model.py, skeleton/local_ai/memory_book.py |
| `cursor/local-proof-planner-f405` | `0e609c1597` | 2026-11-20 | unique content pending port | 9 new files, 8 modified files survive a 3-way merge; open PR #5646 (mergeable) -> cursor/local-desk-model-gapfill-f405; e.g. skeleton/local_ai/desk_journal.py, skeleton/local_ai/desk_model.py, skeleton/local_ai/memory_book.py |
| `cursor/local-review-failclosed-f3f4` | `32a2013df3` | 2026-11-19 | unique content pending port | 4 new files, 18 modified files survive a 3-way merge; open PR #5636 (mergeable) -> cursor/claim-verification-completion-c457; e.g. skeleton/app/local_reviewed_turn.py, skeleton/testing/test_admission_completion_reconciliation.py, skeleton/testing/test_local_review_failclosed.py |
| `cursor/local-reviewed-turn-b4af` | `f219b9eb59` | 2026-11-19 | unique content pending port | 2 new files, 6 modified files survive a 3-way merge; open PR #5629 (mergeable) -> main; e.g. skeleton/app/local_reviewed_turn.py, skeleton/testing/test_local_reviewed_turn.py |
| `cursor/local-tool-stub-gapfill-f405` | `4acc8654b6` | 2026-11-19 | unique content pending port | 4 new files, 7 modified files survive a 3-way merge; open PR #5642 (mergeable) -> main; e.g. skeleton/local_ai/memory_book.py, skeleton/local_ai/multi_turn.py, skeleton/local_ai/office_pack.py |
| `cursor/marathon-authoring-drift-4433` | `99541f68ce` | 2026-11-19 | ported in PR #5771 |  |
| `cursor/marathon-broadphase-mass-4433` | `0e856abd0c` | 2026-11-19 | ported in PR #5771 |  |
| `cursor/marathon-ephemeris-bench-4433` | `6d7cf654f6` | 2026-11-19 | ported in PR #5771 |  |
| `cursor/marathon-evidence-8c4c` | `7d9f3f0370` | 2026-11-19 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge; 11 paths already carried by port PRs |
| `cursor/marathon-hydro-shore-audio-skin-nav-f48c` | `758ce4e376` | 2026-11-19 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge; 7 paths already carried by port PRs |
| `cursor/marathon-integrated-4433` | `053a4cab60` | 2026-11-19 | ported in PR #5771 |  |
| `cursor/marathon-mesh-lod-4433` | `4c99d91de9` | 2026-11-19 | ported in PR #5771 |  |
| `cursor/marathon-registry-readiness-d3c2` | `b37bc2d3ba` | 2026-11-19 | unique content pending port | 1 new files, 6 modified files survive a 3-way merge; 2 paths already carried by port PRs; e.g. tests/test_gf_p0_registry_replay_envelope.py |
| `cursor/marathon-studio-cockpit-431d` | `022b4580db` | 2026-11-19 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge; 18 paths already carried by port PRs |
| `cursor/marathon-temporal-memory-4433` | `9ca4a12644` | 2026-11-19 | ported in PR #5771 |  |
| `cursor/marathon-turbulence-timestep-4433` | `679154830f` | 2026-11-19 | ported in PR #5771 |  |
| `cursor/marathon-world-graph-4433` | `40ae0acafa` | 2026-11-19 | ported in PR #5771 |  |
| `cursor/mass-seam-gapfill-f405` | `b5a60c4f2f` | 2026-11-19 | fully on main | every changed blob already on main |
| `cursor/role-triad-connection-11d5` | `f77c1391d6` | 2026-10-18 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `cursor/skeleton-app-foundation-5f8b` | `fd1415d25a` | 2026-10-17 | nothing unique | superseded: its 11 remaining edits conflict with newer main versions |
| `cursor/studio-office-golden-brief-87f1` | `c3ea598158` | 2026-11-20 | unique content pending port | 16 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5627 (conflicting) -> main; e.g. frontend/app/office.tsx, frontend/scripts/test-studio-office.mjs, frontend/src/features/Office/StudioOfficePanel.styles.ts |
| `data/game-building-corpora` | `51ba74f51a` | 2026-10-15 | unique content pending port | 9 new files, 0 modified files survive a 3-way merge; e.g. data/game_building/math_physics/game_math_physics_corpus.txt, data/game_building/math_physics/math_part_aa, data/game_building/math_physics/math_part_ab |
| `data/game-data-v2-corpora` | `c6e276a4bf` | 2026-10-15 | unique content pending port | 11 new files, 0 modified files survive a 3-way merge; e.g. data/game_data_v2/assets/asset_generation_patterns.txt, data/game_data_v2/assets/asset_part_aa, data/game_data_v2/assets/asset_part_ab |
| `dependabot/docker/frontend/nginx-4c734d3` | `fdf0bb671e` | 2026-11-16 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `dependabot/docker/frontend/nginx-9c68ad4` | `c6df318dc4` | 2026-11-09 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `dependabot/github_actions/actions-207b04f0f6` | `45c6c8f2ff` | 2026-11-05 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `dependabot/github_actions/actions/upload-artifact-7.0.2` | `abb9893542` | 2026-11-16 | fully on main | every changed blob already on main |
| `dependabot/github_actions/gacts/gitleaks-5b59d55fe2d0048f552a22ca2e5c24c5b63c7ecf` | `063fa4f152` | 2026-11-05 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `dependabot/npm_and_yarn/frontend/frontend-react-core-eec9646b84` | `7daa20005c` | 2026-10-28 | unique content pending port | 0 new files, 23 modified files survive a 3-way merge |
| `dependabot/npm_and_yarn/frontend/frontend-react-navigation-7c6e6ac2e4` | `89a54074ac` | 2026-10-26 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `dependabot/npm_and_yarn/frontend/frontend-runtime-4cf0754bda` | `27cefeecf3` | 2026-10-26 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `dependabot/npm_and_yarn/frontend/node-forge-1.4.3` | `f8377b3415` | 2026-11-12 | fully on main | every changed blob already on main |
| `dependabot/pip/pydantic-gte-2.14.1` | `be90e10db1` | 2026-10-26 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `dependabot/pip/root-python-17c1a4b50b` | `f2c7bffcce` | 2026-10-26 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `docs/frontier-consolidation-inventory-80` | `a378a3a8a1` | 2026-10-25 | fully on main | every changed blob already on main |
| `docs/gap-map-20261114` | `27cf4551ab` | 2026-11-14 | fully on main | every changed blob already on main |
| `docs/grokbot-first-completionist-12bot-20261107` | `8c885e4478` | 2026-11-10 | fully on main | every changed blob already on main |
| `docs/masterplan-421-volume-completion-dossiers-20261107` | `19acff286d` | 2026-11-08 | unique content pending port | 9 new files, 52 modified files survive a 3-way merge; 1 paths already carried by port PRs; e.g. skeleton/testing/test_game_project_cli_custody.py, skeleton/testing/test_game_project_cli_input_budget.py, skeleton/testing/test_godot_export_cli_custody.py |
| `docs/studio-durable-producer-qualification-20261030` | `506f422af7` | 2026-10-30 | ported in PR #5767 | all 39 new / 0 modified surviving paths are carried by the port (1 test modules held: fail on source branch too) |
| `docs/studio-source-media-qualification-20261030` | `cb8fafe42a` | 2026-10-30 | ported in PR #5767 | all 54 new / 0 modified surviving paths are carried by the port (6 test modules held: fail on source branch too) |
| `docs/walt-realtime-transport-adr-20261017` | `09ff6dad25` | 2026-10-17 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `draft-hyper-nov2026` | `7613a0c8e5` | 2026-11-12 | fully on main | every changed blob already on main |
| `draft-hyper-nov2026-b` | `81cce27551` | 2026-11-12 | unique content pending port | 18 new files, 0 modified files survive a 3-way merge; e.g. clocked/cockpit/full_critique_81.py, clocked/forge/complete_step_51.py, complete-vision/frontend/bridge.py |
| `draft/ecosystem-full` | `507d3b218e` | 2026-11-04 | nothing unique | generated mass scaffolding (600k+ templated files) / generated docs; not product content |
| `draft/ecosystem-scale-2026-10-29` | `66f5db514d` | 2026-10-31 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. skeleton/jeeves/ecosystem/CATALOG.md |
| `draft/launch-ops-1` | `5eb5326608` | 2026-11-04 | nothing unique | generated mass scaffolding (600k+ templated files) / generated docs; not product content |
| `draft/launch-ops-70k-a` | `990911dedf` | 2026-11-04 | nothing unique | generated mass scaffolding (600k+ templated files) / generated docs; not product content |
| `draft/launch-scale-1` | `950ea6b0cb` | 2026-11-03 | nothing unique | generated mass scaffolding (600k+ templated files) / generated docs; not product content |
| `draft/launch-scale-2` | `86cb8cf3e9` | 2026-11-03 | nothing unique | generated mass scaffolding (600k+ templated files) / generated docs; not product content |
| `draft/launch-scale-3` | `dd33918f67` | 2026-11-03 | nothing unique | generated mass scaffolding (600k+ templated files) / generated docs; not product content |
| `emerald-original-deposit-r1` | `92b869149d` | 2026-11-17 | unique content pending port | 63 new files, 14 modified files survive a 3-way merge; 1 paths already carried by port PRs; e.g. .github/workflows/dragon-atelier-prototype.yml, artifacts/emerald/.gitignore, artifacts/emerald/deposit-r1/.gitattributes |
| `feat/4133-payments-lazy-mongo-backend-20261024` | `ffe3977d27` | 2026-10-25 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `feat/807-b027-lany-20261114` | `006b912977` | 2026-11-14 | fully on main | every changed blob already on main |
| `feat/807-b028-jones-20261024` | `23ddf24a38` | 2026-11-14 | fully on main | every changed blob already on main |
| `feat/807-b030-jones-20261024` | `c47912176c` | 2026-11-14 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `feat/807-b037-jones-20261024` | `350eeb2a68` | 2026-11-14 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `feat/807-net-w1-walt-20261024` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/807-world-backend-20261024` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/admission-lease-failclosed-20261105` | `8fcd9d07fb` | 2026-11-14 | unique content pending port | 0 new files, 2 modified files survive a 3-way merge |
| `feat/adventure-systems-depth` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/ai-authorized-artifact-workspace-20261103` | `9b85ecf549` | 2026-11-14 | nothing unique | superseded: its 22 remaining edits conflict with newer main versions |
| `feat/ai-cognition-wave-01-20261103` | `3159682624` | 2026-11-14 | fully on main | every changed blob already on main |
| `feat/ai-cognition-wave-02-20261103` | `3159682624` | 2026-11-14 | fully on main | every changed blob already on main |
| `feat/ai-cognition-wave-03-20261103` | `3159682624` | 2026-11-14 | fully on main | every changed blob already on main |
| `feat/ai-cognition-wave-04-20261103` | `3159682624` | 2026-11-14 | fully on main | every changed blob already on main |
| `feat/ai-cognition-wave-05-20261103` | `9b85ecf549` | 2026-11-14 | nothing unique | superseded: its 22 remaining edits conflict with newer main versions |
| `feat/ai-cognition-wave-06-20261103` | `9b85ecf549` | 2026-11-14 | nothing unique | superseded: its 22 remaining edits conflict with newer main versions |
| `feat/ai-cognition-wave-07-20261103` | `9b85ecf549` | 2026-11-14 | nothing unique | superseded: its 22 remaining edits conflict with newer main versions |
| `feat/ai-cognition-wave-08-20261103` | `9b85ecf549` | 2026-11-14 | nothing unique | superseded: its 22 remaining edits conflict with newer main versions |
| `feat/ai-durable-signed-work-orders-20261103` | `9b85ecf549` | 2026-11-14 | nothing unique | superseded: its 22 remaining edits conflict with newer main versions |
| `feat/ai-ecosystem-1p9gb-ordered-bundle-20261102` | `9b85ecf549` | 2026-11-14 | nothing unique | superseded: its 22 remaining edits conflict with newer main versions |
| `feat/ai-ecosystem-operational-assurance-50-planes-20261031` | `214c7a4a1f` | 2026-11-14 | fully on main | every changed blob already on main |
| `feat/ai-first-laptop-source-preflight-20261103` | `9b85ecf549` | 2026-11-14 | nothing unique | superseded: its 22 remaining edits conflict with newer main versions |
| `feat/ai-genesis-native-weights-20261103-r2` | `9b85ecf549` | 2026-11-14 | nothing unique | superseded: its 22 remaining edits conflict with newer main versions |
| `feat/ai-integral-runtime-guard-matrix-20261103` | `9b85ecf549` | 2026-11-14 | nothing unique | superseded: its 22 remaining edits conflict with newer main versions |
| `feat/ai-laptop-first-usable-20261103` | `9b85ecf549` | 2026-11-14 | nothing unique | superseded: its 22 remaining edits conflict with newer main versions |
| `feat/ai-native-grounded-manifest-cli-20261103` | `9b85ecf549` | 2026-11-14 | nothing unique | superseded: its 22 remaining edits conflict with newer main versions |
| `feat/ai-native-qualification-evidence-20261103` | `9b85ecf549` | 2026-11-14 | nothing unique | superseded: its 22 remaining edits conflict with newer main versions |
| `feat/ai-native-supervised-alignment-20261103-r3` | `9b85ecf549` | 2026-11-14 | nothing unique | superseded: its 22 remaining edits conflict with newer main versions |
| `feat/ai-production-trust-gates-20261103` | `f7070a9fcf` | 2026-11-05 | nothing unique | superseded: its 160 remaining edits conflict with newer main versions |
| `feat/ai-reliability-fabric-40-20261103` | `f277e4ed2b` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/ai-reliability-fabric-native-20261103` | `1ce349e21e` | 2026-11-05 | nothing unique | superseded: its 160 remaining edits conflict with newer main versions |
| `feat/app-foundation-realtime` | `3dfd2b1176` | 2026-11-14 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `feat/app-foundation-realtime-v2` | `5836c4ae95` | 2026-11-14 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `feat/app-foundation-shell` | `3dfd2b1176` | 2026-11-14 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `feat/app-foundation-shell-2` | `5836c4ae95` | 2026-11-14 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `feat/app-foundation-shell-2b` | `3dfd2b1176` | 2026-11-14 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `feat/canon-custody-50-continuity-policies-20261031` | `2a6cb00ccf` | 2026-11-14 | fully on main | every changed blob already on main |
| `feat/character-arc` | `e924431380` | 2026-11-19 | unique content pending port | 2 new files, 0 modified files survive a 3-way merge; open PR #5693 (mergeable) -> main; e.g. docs/creation/CHARACTER_ARC.md, skeleton/ai/agents/jeeves/character_arc.py |
| `feat/choice-ledger-20261031` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/chronological-academy-source-bound-study-20261115` | `8f6e8ce8e5` | 2026-11-16 | fully on main | every changed blob already on main |
| `feat/chronological-audit-cns-runtime-20261115` | `80ef26a172` | 2026-11-16 | fully on main | every changed blob already on main |
| `feat/chronological-engine-coverage-evidence-20261115` | `7164459687` | 2026-11-20 | unique content pending port | 5 new files, 2 modified files survive a 3-way merge; open PR #5436 (mergeable) -> fix/chronological-coverage-evidence-20261115; e.g. backend/gameforge/coverage_inventory.py, backend/tests/test_chronological_coverage_inventory.py, backend/tests/test_chronological_gameforge_coverage.py |
| `feat/ci-backend-test-drift-devops-20261031` | `d8168b3823` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/ci-jeeves-contracts-glenny-20261031` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/ci-jest-devops-20261031` | `bbb07ed733` | 2026-10-31 | unique content pending port | 3 new files, 0 modified files survive a 3-way merge; e.g. .github/workflows/frontend-jest.yml, backend/tests/test_frontend_jest_workflow_contract.py, frontend/jest.config.js |
| `feat/ci-run-paths-devops-20261031` | `1a58f61222` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/ci-test-paths-devops-20261031` | `a7e2028365` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/client-projects-20261017` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/client-realtime-wire-20261017` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/client-sdk-20261017` | `d523096a4c` | 2026-11-14 | fully on main | every changed blob already on main |
| `feat/design-bible-asset-depth` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/devops-app-foundation-e2e` | `f66f3160f2` | 2026-10-17 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `feat/devops-appfoundation-envs` | `2d722ca132` | 2026-10-17 | ported in PR #5771 | all 0 new / 1 modified surviving paths are carried by the port |
| `feat/devops-appfoundation-observability` | `b7d84fb3c3` | 2026-10-17 | fully on main | every changed blob already on main |
| `feat/devops-appfoundation-release` | `1d8f91fde0` | 2026-10-17 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `feat/devops-automerge-contract-schedule-optional` | `932a264b6b` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/devops-merge-readiness-app-foundation` | `d59f27f429` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/devops-perf-budgets-json-limit` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/devops-status-grenn-20261024` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/dialogue-sessions-50-scene-directors-20261031` | `2a6cb00ccf` | 2026-11-14 | fully on main | every changed blob already on main |
| `feat/director-interactive-runtime-export-dragon-feedback-20261016` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/discourse-mainline-surface-convergence-20261110-r01` | `cff966df45` | 2026-11-11 | nothing unique | superseded: its 17 remaining edits conflict with newer main versions |
| `feat/docker-local-ai-assurance-20261119-r01` | `3b84b87d30` | 2026-11-20 | unique content pending port | 69 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5632 (mergeable) -> feat/docker-local-ai-guarded-offline-launch-20261119-r01; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-assurance-ci-20261119-r01` | `c601ca11bb` | 2026-11-20 | unique content pending port | 69 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5633 (conflicting) -> main; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-assurance-ci-20261119-r02` | `c298d58398` | 2026-11-20 | unique content pending port | 72 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5635 (conflicting) -> main; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-auth-principal-custody-20261120-r01` | `c37431ef19` | 2026-11-20 | unique content pending port | 80 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5697 (mergeable) -> feat/docker-local-ai-protected-chat-qualification-20261120-r01; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-canonical-mutator-census-20261120-r01` | `afdf34e77a` | 2026-11-20 | unique content pending port | 96 new files, 25 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5716 (mergeable) -> feat/docker-local-ai-real-writer-journal-admission-20261120-r01; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-canonical-mutator-census-ci-20261120-r01` | `afdf34e77a` | 2026-11-20 | unique content pending port | 96 new files, 25 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5717 (conflicting) -> main; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-chat-ci-20261120-r01` | `9823bf55d7` | 2026-11-20 | unique content pending port | 80 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5696 (conflicting) -> main; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-chat-ci-20261120-r02` | `c37431ef19` | 2026-11-20 | unique content pending port | 80 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5698 (conflicting) -> main; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-chat-ci-20261120-r03` | `fa6e0bb817` | 2026-11-20 | unique content pending port | 80 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5700 (conflicting) -> main; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-chat-ci-20261120-r04` | `ff09e9895f` | 2026-11-20 | unique content pending port | 83 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5702 (conflicting) -> main; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-chroma-index-custody-20261120-r01` | `07ad5253ad` | 2026-11-20 | unique content pending port | 103 new files, 25 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5722 (mergeable) -> feat/docker-local-ai-verified-sqlite-rehydration-20261120-r01; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-chroma-index-custody-ci-20261120-r01` | `07ad5253ad` | 2026-11-20 | unique content pending port | 103 new files, 25 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5723 (conflicting) -> main; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-compose-ci-20261119-r01` | `10ac50da71` | 2026-11-19 | unique content pending port | 58 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5623 (conflicting) -> main; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-compose-ci-20261119-r02` | `606cce9b5f` | 2026-11-19 | unique content pending port | 58 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5624 (conflicting) -> main; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-compose-ci-20261119-r04` | `6c2ebbd1b6` | 2026-11-19 | unique content pending port | 61 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5626 (conflicting) -> main; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-double-signed-custody-20261120-r01` | `4042329fbd` | 2026-11-20 | unique content pending port | 115 new files, 25 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5730 (mergeable) -> feat/docker-local-ai-mongo-wiredtiger-custody-20261120-r01; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-double-signed-custody-ci-20261120-r01` | `4042329fbd` | 2026-11-20 | unique content pending port | 115 new files, 25 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5731 (conflicting) -> main; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-dual-service-live-journal-audit-20261120-r01` | `4ed5f7d042` | 2026-11-20 | unique content pending port | 97 new files, 25 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5714 (conflicting) -> feat/docker-local-ai-real-writer-journal-admission-20261120-r01; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-dual-service-live-journal-audit-ci-20261120-r01` | `4ed5f7d042` | 2026-11-20 | unique content pending port | 97 new files, 25 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5715 (conflicting) -> main; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-four-service-ci-20261119-r01` | `ed285fe99e` | 2026-11-19 | unique content pending port | 75 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5638 (conflicting) -> main; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-guard-dominance-20261120-r01` | `953fa61caa` | 2026-11-20 | unique content pending port | 97 new files, 25 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5718 (mergeable) -> feat/docker-local-ai-canonical-mutator-census-20261120-r01; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-guard-dominance-ci-20261120-r01` | `953fa61caa` | 2026-11-20 | unique content pending port | 97 new files, 25 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5719 (conflicting) -> main; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-guarded-offline-launch-20261119-r01` | `6c2ebbd1b6` | 2026-11-19 | unique content pending port | 61 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5625 (mergeable) -> feat/docker-local-ai-offline-compose-binding-20261119-r01; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-host-loopback-20261120-r01` | `fa6e0bb817` | 2026-11-20 | unique content pending port | 80 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5699 (mergeable) -> feat/docker-local-ai-auth-principal-custody-20261120-r01; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-independent-provenance-20261119-r01` | `5313157482` | 2026-11-20 | unique content pending port | 72 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5634 (mergeable) -> feat/docker-local-ai-assurance-20261119-r01; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-minority-fencing-20261120-r01` | `e5a40ac5bc` | 2026-11-20 | unique content pending port | 86 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5705 (conflicting) -> feat/docker-local-ai-mongo-synthetic-failover-20261120-r01; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-minority-fencing-ci-20261120-r01` | `e5a40ac5bc` | 2026-11-20 | unique content pending port | 86 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5706 (conflicting) -> main; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-mongo-majority-admission-20261120-r01` | `ff09e9895f` | 2026-11-20 | unique content pending port | 83 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5701 (mergeable) -> feat/docker-local-ai-host-loopback-20261120-r01; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-mongo-synthetic-failover-20261120-r01` | `8238b0e248` | 2026-11-20 | unique content pending port | 86 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5703 (mergeable) -> feat/docker-local-ai-mongo-majority-admission-20261120-r01; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-mongo-synthetic-failover-ci-20261120-r01` | `8238b0e248` | 2026-11-20 | unique content pending port | 86 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5704 (conflicting) -> main; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-mongo-wiredtiger-custody-20261120-r01` | `59235475f1` | 2026-11-20 | unique content pending port | 112 new files, 25 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5728 (mergeable) -> feat/docker-local-ai-offline-recovery-evidence-ledger-20261120-r01; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-mongo-wiredtiger-custody-ci-20261120-r01` | `59235475f1` | 2026-11-20 | unique content pending port | 112 new files, 25 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5729 (conflicting) -> main; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-native-pressure-20261120-r01` | `9823bf55d7` | 2026-11-20 | unique content pending port | 80 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-offline-compose-binding-20261119-r01` | `606cce9b5f` | 2026-11-19 | unique content pending port | 58 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5622 (mergeable) -> feat/docker-local-ai-offline-images-20261119-r01; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-offline-images-20261119-r01` | `fd47c01e66` | 2026-11-19 | unique content pending port | 54 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5617 (mergeable) -> feat/docker-local-ai-runtime-20261117-r01; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-offline-recovery-evidence-ledger-20261120-r01` | `d4e9e2a175` | 2026-11-20 | unique content pending port | 107 new files, 25 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5726 (mergeable) -> fix/docker-local-ai-chroma-dirfd-index-race-20261120-r01; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-offline-recovery-evidence-ledger-ci-20261120-r01` | `d4e9e2a175` | 2026-11-20 | unique content pending port | 107 new files, 25 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5727 (conflicting) -> main; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-physical-four-service-20261119-r01` | `a5f6c4059a` | 2026-11-20 | unique content pending port | 75 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5637 (mergeable) -> feat/docker-local-ai-independent-provenance-20261119-r01; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-physical-synthetic-mongo-restart-20261120-r01` | `27dbdcdb33` | 2026-11-20 | unique content pending port | 116 new files, 25 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5734 (mergeable) -> fix/docker-local-ai-mongo-restore-root-dirfd-20261120-r01; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-physical-synthetic-mongo-restart-ci-20261120-r01` | `27dbdcdb33` | 2026-11-20 | unique content pending port | 116 new files, 25 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5735 (conflicting) -> main; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-protected-chat-qualification-20261120-r01` | `9823bf55d7` | 2026-11-20 | unique content pending port | 80 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5695 (mergeable) -> feat/docker-local-ai-physical-four-service-20261119-r01; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-real-writer-journal-admission-20261120-r01` | `7da7cbb3f3` | 2026-11-20 | unique content pending port | 93 new files, 25 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5712 (mergeable) -> feat/docker-local-ai-synthetic-writer-epoch-20261120-r01; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-real-writer-journal-admission-ci-20261120-r01` | `7da7cbb3f3` | 2026-11-20 | unique content pending port | 93 new files, 25 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5713 (conflicting) -> main; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-runtime-20261117-r01` | `150a71c173` | 2026-11-19 | unique content pending port | 47 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5591 (conflicting) -> main; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-runtime-ci-20261119-r02` | `fd47c01e66` | 2026-11-19 | unique content pending port | 54 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5618 (conflicting) -> main; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-synthetic-writer-epoch-20261120-r01` | `005e54042f` | 2026-11-20 | unique content pending port | 89 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5710 (mergeable) -> fix/docker-local-ai-mongo-real-quorum-semantics-20261120-r01; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-synthetic-writer-epoch-ci-20261120-r01` | `005e54042f` | 2026-11-20 | unique content pending port | 89 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5711 (conflicting) -> main; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-verified-sqlite-rehydration-20261120-r01` | `6f1d8b799c` | 2026-11-20 | unique content pending port | 100 new files, 25 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5720 (mergeable) -> feat/docker-local-ai-guard-dominance-20261120-r01; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/docker-local-ai-verified-sqlite-rehydration-ci-20261120-r01` | `6f1d8b799c` | 2026-11-20 | unique content pending port | 100 new files, 25 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5721 (conflicting) -> main; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `feat/dragon-access-resilience-20261116` | `4c63e6af95` | 2026-11-16 | unique content pending port | 76 new files, 31 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5458 (mergeable) -> feat/dragon-restorative-runtime-20261115; e.g. .github/workflows/dragon-hoarder-qualification.yml, backend/core/dragon_checkpoint_replica.py, backend/core/dragon_deep_archive.py |
| `feat/dragon-acquisition-federation-convergence-20261116` | `48bc3a3c9b` | 2026-11-16 | unique content pending port | 217 new files, 37 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5463 (mergeable) -> feat/dragon-offline-export-integrity-20261116; e.g. .github/workflows/dragon-hoarder-qualification.yml, backend/core/dragon_application_backup.py, backend/core/dragon_authorized_api.py |
| `feat/dragon-audiovisual-intelligence-20261115` | `06bfbe3a66` | 2026-11-16 | unique content pending port | 118 new files, 35 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5440 (conflicting) -> feat/dragon-hoarder-game-corpus-20261115; e.g. .github/workflows/dragon-hoarder-qualification.yml, backend/core/dragon_checkpoint_replica.py, backend/core/dragon_cold_primary.py |
| `feat/dragon-canonical-graph-authority-lanes-20261116` | `9e98d16cf7` | 2026-11-16 | unique content pending port | 179 new files, 35 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5448 (mergeable) -> feat/dragon-intra-owner-manifest-write-lanes-20261116; e.g. .github/workflows/dragon-hoarder-qualification.yml, backend/core/dragon_bundled_steam_leads.py, backend/core/dragon_catalogue_snapshots/steam-games-000.jsonl |
| `feat/dragon-crawler-deep-campaign-20261106` | `2cb5ad0aa2` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/dragon-deep-archive-hoag-wiki-20261115` | `ba6faac98f` | 2026-11-16 | unique content pending port | 74 new files, 35 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5438 (conflicting) -> feat/dragon-restorative-runtime-20261115; e.g. .github/workflows/dragon-hoarder-qualification.yml, backend/core/dragon_checkpoint_replica.py, backend/core/dragon_deep_archive.py |
| `feat/dragon-deployment-custody-qualification-20261116` | `be52738a50` | 2026-11-16 | unique content pending port | 190 new files, 35 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5454 (mergeable) -> feat/dragon-same-owner-concurrent-reservations-20261116; e.g. .github/workflows/dragon-hoarder-qualification.yml, backend/core/dragon_bundled_steam_leads.py, backend/core/dragon_catalogue_snapshots/steam-games-000.jsonl |
| `feat/dragon-derived-index-rebuild-custody-20261116` | `3d0131e6a0` | 2026-11-16 | unique content pending port | 202 new files, 36 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5457 (conflicting) -> feat/dragon-mongo-offline-relocation-20261116; e.g. .github/workflows/dragon-hoarder-qualification.yml, backend/core/dragon_bundled_steam_leads.py, backend/core/dragon_catalogue_snapshots/steam-games-000.jsonl |
| `feat/dragon-ecosystem-storage-custody-20261116` | `0b21de60ae` | 2026-11-16 | unique content pending port | 193 new files, 35 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5455 (mergeable) -> feat/dragon-deployment-custody-qualification-20261116; e.g. .github/workflows/dragon-hoarder-qualification.yml, backend/core/dragon_bundled_steam_leads.py, backend/core/dragon_catalogue_snapshots/steam-games-000.jsonl |
| `feat/dragon-global-game-source-federation-20261115` | `363f6aed1e` | 2026-11-20 | unique content pending port | 122 new files, 35 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5441 (mergeable) -> feat/dragon-hoarder-game-corpus-20261115; e.g. .github/workflows/dragon-hoarder-qualification.yml, backend/core/dragon_checkpoint_replica.py, backend/core/dragon_cold_primary.py |
| `feat/dragon-hoarder-game-corpus-20261115` | `aecb6b782e` | 2026-11-20 | unique content pending port | 115 new files, 35 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5439 (mergeable) -> feat/dragon-deep-archive-hoag-wiki-20261115; e.g. .github/workflows/dragon-hoarder-qualification.yml, backend/core/dragon_checkpoint_replica.py, backend/core/dragon_cold_primary.py |
| `feat/dragon-independent-canonical-review-writers-20261116` | `2a2002a003` | 2026-11-16 | unique content pending port | 182 new files, 35 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5449 (mergeable) -> feat/dragon-canonical-graph-authority-lanes-20261116; e.g. .github/workflows/dragon-hoarder-qualification.yml, backend/core/dragon_bundled_steam_leads.py, backend/core/dragon_catalogue_snapshots/steam-games-000.jsonl |
| `feat/dragon-industrial-catalogue-scale-20261116` | `e028f4bc07` | 2026-11-16 | unique content pending port | 161 new files, 35 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5443 (conflicting) -> feat/dragon-modding-seed-expansion-20261116; e.g. .github/workflows/dragon-hoarder-qualification.yml, backend/core/dragon_bundled_steam_leads.py, backend/core/dragon_catalogue_snapshots/steam-games-000.jsonl |
| `feat/dragon-intra-owner-manifest-write-lanes-20261116` | `892f16b307` | 2026-11-16 | unique content pending port | 176 new files, 35 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5447 (mergeable) -> feat/dragon-owner-migration-index-fabric-20261116; e.g. .github/workflows/dragon-hoarder-qualification.yml, backend/core/dragon_bundled_steam_leads.py, backend/core/dragon_catalogue_snapshots/steam-games-000.jsonl |
| `feat/dragon-jeeves-discourse-link-backlog-20261117` | `cdcb212869` | 2026-11-17 | unique content pending port | 292 new files, 39 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5495 (mergeable) -> feat/dragon-acquisition-federation-convergence-20261116; e.g. .github/workflows/dragon-contextual-campaign-qualification.yml, .github/workflows/dragon-ensemble-storage-qualification.yml, .github/workflows/dragon-hoarder-qualification.yml |
| `feat/dragon-modding-seed-expansion-20261116` | `b36c35fcfc` | 2026-11-16 | unique content pending port | 130 new files, 35 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5442 (mergeable) -> feat/dragon-global-game-source-federation-20261115; e.g. .github/workflows/dragon-hoarder-qualification.yml, backend/core/dragon_checkpoint_replica.py, backend/core/dragon_cold_primary.py |
| `feat/dragon-mongo-offline-relocation-20261116` | `56ef7df6ac` | 2026-11-16 | unique content pending port | 197 new files, 36 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5456 (conflicting) -> feat/dragon-ecosystem-storage-custody-20261116; e.g. .github/workflows/dragon-hoarder-qualification.yml, backend/core/dragon_bundled_steam_leads.py, backend/core/dragon_catalogue_snapshots/steam-games-000.jsonl |
| `feat/dragon-multi-batch-root-settlement-20261116` | `1ad399aa74` | 2026-11-16 | unique content pending port | 186 new files, 35 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5452 (mergeable) -> feat/dragon-snapshot-feed-parallel-settlement-20261116; e.g. .github/workflows/dragon-hoarder-qualification.yml, backend/core/dragon_bundled_steam_leads.py, backend/core/dragon_catalogue_snapshots/steam-games-000.jsonl |
| `feat/dragon-offline-export-integrity-20261116` | `146e2d9cd2` | 2026-11-16 | unique content pending port | 185 new files, 35 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5462 (mergeable) -> feat/dragon-parallel-canonical-structural-settlement-20261116; e.g. .github/workflows/dragon-hoarder-qualification.yml, backend/core/dragon_bundled_steam_leads.py, backend/core/dragon_catalogue_snapshots/steam-games-000.jsonl |
| `feat/dragon-owner-migration-index-fabric-20261116` | `917ab52125` | 2026-11-16 | unique content pending port | 170 new files, 35 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5446 (mergeable) -> feat/dragon-physical-ledger-shards-20261116; e.g. .github/workflows/dragon-hoarder-qualification.yml, backend/core/dragon_bundled_steam_leads.py, backend/core/dragon_catalogue_snapshots/steam-games-000.jsonl |
| `feat/dragon-parallel-canonical-structural-settlement-20261116` | `c5068bb116` | 2026-11-16 | unique content pending port | 185 new files, 35 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5450 (mergeable) -> feat/dragon-independent-canonical-review-writers-20261116; e.g. .github/workflows/dragon-hoarder-qualification.yml, backend/core/dragon_bundled_steam_leads.py, backend/core/dragon_catalogue_snapshots/steam-games-000.jsonl |
| `feat/dragon-physical-ledger-shards-20261116` | `e8f6202914` | 2026-11-16 | unique content pending port | 167 new files, 35 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5445 (mergeable) -> feat/dragon-tenfold-shard-fabric-20261116; e.g. .github/workflows/dragon-hoarder-qualification.yml, backend/core/dragon_bundled_steam_leads.py, backend/core/dragon_catalogue_snapshots/steam-games-000.jsonl |
| `feat/dragon-research-archives-wave24-20261107` | `312b047c3b` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/dragon-research-pilot-qualification-20261112` | `6e9b1eff78` | 2026-11-14 | ported in PR #5771 | all 0 new / 1 modified surviving paths are carried by the port |
| `feat/dragon-restorative-runtime-20261115` | `63a87120ee` | 2026-11-16 | unique content pending port | 75 new files, 30 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5429 (conflicting) -> main; e.g. .github/workflows/dragon-hoarder-qualification.yml, backend/core/dragon_checkpoint_replica.py, backend/core/dragon_deep_archive.py |
| `feat/dragon-same-owner-concurrent-reservations-20261116` | `8a310ee732` | 2026-11-16 | unique content pending port | 187 new files, 35 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5453 (mergeable) -> feat/dragon-multi-batch-root-settlement-20261116; e.g. .github/workflows/dragon-hoarder-qualification.yml, backend/core/dragon_bundled_steam_leads.py, backend/core/dragon_catalogue_snapshots/steam-games-000.jsonl |
| `feat/dragon-snapshot-feed-parallel-settlement-20261116` | `33282775a5` | 2026-11-16 | unique content pending port | 185 new files, 35 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5451 (mergeable) -> feat/dragon-parallel-canonical-structural-settlement-20261116; e.g. .github/workflows/dragon-hoarder-qualification.yml, backend/core/dragon_bundled_steam_leads.py, backend/core/dragon_catalogue_snapshots/steam-games-000.jsonl |
| `feat/dragon-tenfold-shard-fabric-20261116` | `4725607956` | 2026-11-16 | unique content pending port | 163 new files, 35 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5444 (mergeable) -> feat/dragon-industrial-catalogue-scale-20261116; e.g. .github/workflows/dragon-hoarder-qualification.yml, backend/core/dragon_bundled_steam_leads.py, backend/core/dragon_catalogue_snapshots/steam-games-000.jsonl |
| `feat/emerald-asset-custody-20261117` | `95230ad6f8` | 2026-11-17 | unique content pending port | 5 new files, 3 modified files survive a 3-way merge; open PR #5499 (conflicting) -> main; e.g. docs/EMERALD_OFFLINE_ASSETS.md, frontend/public/emerald/.gitignore, frontend/scripts/install_emerald_assets.py |
| `feat/emerald-binary-publication-20261117` | `1f815fc4d8` | 2026-11-17 | unique content pending port | 68 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5532 (mergeable) -> feat/emerald-original-model-audit-conveyor-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-original-publication.yml, artifacts/emerald/.gitignore |
| `feat/emerald-browser-deposit-import-20261117` | `bd8f7d5406` | 2026-11-17 | unique content pending port | 64 new files, 14 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5526 (mergeable) -> fix/emerald-final-forge-roundtrip-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, artifacts/emerald/.gitignore, docs/DRAGON_ATELIER_INSPECTION_LAB.md |
| `feat/emerald-capture-projection-20261117` | `e921832360` | 2026-11-17 | unique content pending port | 8 new files, 0 modified files survive a 3-way merge; open PR #5500 (mergeable) -> feat/emerald-asset-custody-20261117; e.g. docs/EMERALD_OFFLINE_ASSETS.md, frontend/public/emerald/.gitignore, frontend/scripts/install_emerald_assets.py |
| `feat/emerald-exact-binary-reconstruction-20261117` | `2511ab26d2` | 2026-11-17 | unique content pending port | 56 new files, 6 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5524 (mergeable) -> fix/emerald-recovered-archive-qualification-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, artifacts/emerald/.gitignore, docs/DRAGON_ATELIER_INSPECTION_LAB.md |
| `feat/emerald-five-evolution-models-20261117` | `307e22ae48` | 2026-11-17 | unique content pending port | 74 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5541 (mergeable) -> feat/emerald-original-model-audit-conveyor-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, artifacts/emerald/.gitignore |
| `feat/emerald-integration-qualification-20261117` | `31d84b9448` | 2026-11-17 | unique content pending port | 19 new files, 4 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5503 (mergeable) -> feat/emerald-native-qualification-20261117; e.g. artifacts/emerald/.gitignore, docs/EMERALD_CRAWLER_PRESENTATION.md, docs/EMERALD_INTEGRATION_ACCEPTANCE.md |
| `feat/emerald-lfs-transfer-custody-20261117` | `6fa4204681` | 2026-11-17 | unique content pending port | 60 new files, 14 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5523 (mergeable) -> fix/emerald-original-binary-recovered-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, artifacts/emerald/.gitignore, docs/DRAGON_ATELIER_INSPECTION_LAB.md |
| `feat/emerald-live-renderer-20261117` | `fad6fbe9ce` | 2026-11-17 | unique content pending port | 13 new files, 2 modified files survive a 3-way merge; open PR #5501 (mergeable) -> feat/emerald-capture-projection-20261117; e.g. docs/EMERALD_CRAWLER_PRESENTATION.md, docs/EMERALD_OFFLINE_ASSETS.md, frontend/public/emerald/.gitignore |
| `feat/emerald-mesh-skin-audit-20261117` | `5bd6628b96` | 2026-11-17 | unique content pending port | 42 new files, 6 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5515 (mergeable) -> feat/emerald-visual-playback-lab-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, artifacts/emerald/.gitignore, docs/DRAGON_ATELIER_INSPECTION_LAB.md |
| `feat/emerald-native-material-audit-20261117` | `6ad88de614` | 2026-11-17 | unique content pending port | 45 new files, 6 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5516 (mergeable) -> feat/emerald-mesh-skin-audit-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, artifacts/emerald/.gitignore, docs/DRAGON_ATELIER_INSPECTION_LAB.md |
| `feat/emerald-native-qualification-20261117` | `03dd1f0f29` | 2026-11-17 | unique content pending port | 18 new files, 2 modified files survive a 3-way merge; open PR #5502 (mergeable) -> feat/emerald-live-renderer-20261117; e.g. artifacts/emerald/.gitignore, docs/EMERALD_CRAWLER_PRESENTATION.md, docs/EMERALD_NATIVE_QUALIFICATION.md |
| `feat/emerald-native-staging-verifier-20261117` | `e243104b7e` | 2026-11-17 | unique content pending port | 60 new files, 6 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5528 (mergeable) -> feat/emerald-offline-delivery-transaction-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, artifacts/emerald/.gitignore, docs/DRAGON_ATELIER_INSPECTION_LAB.md |
| `feat/emerald-offline-delivery-transaction-20261117` | `fd69068a85` | 2026-11-17 | unique content pending port | 58 new files, 6 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5527 (mergeable) -> feat/emerald-exact-binary-reconstruction-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, artifacts/emerald/.gitignore, docs/DRAGON_ATELIER_INSPECTION_LAB.md |
| `feat/emerald-original-animation-audit-20261117` | `c1b37dde8a` | 2026-11-17 | unique content pending port | 37 new files, 6 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5513 (mergeable) -> fix/emerald-device-admission-preflight-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, artifacts/emerald/.gitignore, docs/DRAGON_ATELIER_INSPECTION_LAB.md |
| `feat/emerald-original-model-audit-conveyor-20261117` | `235e92e75d` | 2026-11-17 | unique content pending port | 63 new files, 13 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5531 (mergeable) -> fix/emerald-inherited-forge-ssr-custody-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, artifacts/emerald/.gitignore, docs/DRAGON_ATELIER_INSPECTION_LAB.md |
| `feat/emerald-poster-v4-anatomical-custody-20261117` | `1abda6183d` | 2026-11-17 | unique content pending port | 80 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5550 (mergeable) -> fix/emerald-evolution-exact-head-ci-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `feat/emerald-scholar-wingfold-r1-20261117` | `9fda63f850` | 2026-11-20 | unique content pending port | 102 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5559 (mergeable) -> fix/emerald-v4-provisional-motion-hold-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `feat/emerald-v3-draft-publication-custody-20261117` | `761ea9e47c` | 2026-11-17 | unique content pending port | 79 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5543 (mergeable) -> feat/emerald-weighted-developmental-evolutions-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-weighted-publication.yml |
| `feat/emerald-v4-triangle-contact-gate-20261117` | `8025086706` | 2026-11-17 | unique content pending port | 93 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5557 (mergeable) -> feat/emerald-v4-unreal-device-qualification-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `feat/emerald-v4-unreal-device-qualification-20261117` | `013e3c15b5` | 2026-11-17 | unique content pending port | 86 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5556 (mergeable) -> feat/emerald-poster-v4-anatomical-custody-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `feat/emerald-v5-contact-coverage-worklist-20261117` | `1d4f736089` | 2026-11-17 | unique content pending port | 118 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5568 (mergeable) -> feat/emerald-v5-proximal-wingfold-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `feat/emerald-v5-proximal-wingfold-20261117` | `b0d9f0e9ee` | 2026-11-17 | unique content pending port | 107 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5565 (mergeable) -> feat/emerald-v5-scholar-wingfold-custody-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `feat/emerald-v5-scholar-wingfold-custody-20261117` | `15da02cf99` | 2026-11-17 | unique content pending port | 98 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5563 (mergeable) -> feat/emerald-v4-unreal-device-qualification-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `feat/emerald-v6-crossfade-contact-qualification-20261117` | `4735235a91` | 2026-11-17 | unique content pending port | 137 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5576 (mergeable) -> feat/emerald-v6-exact-binary-transport-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `feat/emerald-v6-exact-binary-transport-20261117` | `c63f71ec93` | 2026-11-17 | unique content pending port | 130 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5570 (mergeable) -> feat/emerald-v6-tail-root-collision-repair-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `feat/emerald-v6-tail-root-collision-repair-20261117` | `38e4ebe1d2` | 2026-11-17 | unique content pending port | 125 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5569 (mergeable) -> feat/emerald-v5-contact-coverage-worklist-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `feat/emerald-v7-binary-custody-20261117` | `9a8bf42200` | 2026-11-17 | unique content pending port | 151 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5578 (mergeable) -> feat/emerald-v7-orbit02-tail-closure-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `feat/emerald-v7-failure-custody-20261118` | `7f3f0f390b` | 2026-11-18 | unique content pending port | 206 new files, 12 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5612 (mergeable) -> feat/emerald-v7-three-pose-parity-20261118; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `feat/emerald-v7-nine-phase-qualification-20261117` | `13a87f88e3` | 2026-11-17 | unique content pending port | 156 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5581 (mergeable) -> feat/emerald-v7-binary-custody-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `feat/emerald-v7-orbit02-tail-closure-20261117` | `80236043f4` | 2026-11-17 | unique content pending port | 146 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5577 (mergeable) -> feat/emerald-v6-crossfade-contact-qualification-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `feat/emerald-v7-original-mixer-binding-census-20261118` | `d03e56725c` | 2026-11-18 | unique content pending port | 205 new files, 12 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5602 (mergeable) -> feat/emerald-v7-three-execution-conveyor-20261118; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `feat/emerald-v7-qualified-offline-replay-20261117` | `03b3e79f1b` | 2026-11-17 | unique content pending port | 166 new files, 12 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5588 (mergeable) -> fix/emerald-v7-registered-ci-gates-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `feat/emerald-v7-quarantined-original-delivery-20261117` | `d63e9ea0f2` | 2026-11-17 | unique content pending port | 185 new files, 12 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5592 (mergeable) -> feat/emerald-v7-remote-binary-reassembly-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `feat/emerald-v7-real-mixer-pair-admission-20261118` | `f50189b73d` | 2026-11-18 | unique content pending port | 196 new files, 12 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5597 (mergeable) -> feat/emerald-v7-three-mixer-joint-traces-20261118; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `feat/emerald-v7-remote-binary-reassembly-20261117` | `bcfa20cfd0` | 2026-11-17 | unique content pending port | 181 new files, 12 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5590 (mergeable) -> test/emerald-v7-independent-binary-recheck-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `feat/emerald-v7-reviewed-contact-toolchain-20261117` | `b22e702622` | 2026-11-17 | unique content pending port | 161 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5586 (mergeable) -> fix/emerald-v7-nine-phase-report-contract-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `feat/emerald-v7-three-execution-conveyor-20261118` | `2f119f0102` | 2026-11-18 | unique content pending port | 200 new files, 12 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5601 (mergeable) -> feat/emerald-v7-real-mixer-pair-admission-20261118; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `feat/emerald-v7-three-mixer-joint-traces-20261118` | `fa23316409` | 2026-11-18 | unique content pending port | 192 new files, 12 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5596 (mergeable) -> feat/emerald-v7-quarantined-original-delivery-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `feat/emerald-v7-three-pose-parity-20261118` | `fe250bc44f` | 2026-11-18 | unique content pending port | 204 new files, 12 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5611 (mergeable) -> feat/emerald-v7-three-execution-conveyor-20261118; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `feat/emerald-v7-two-model-evidence-revalidation-20261118` | `7b741fa830` | 2026-11-18 | unique content pending port | 209 new files, 12 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5603 (mergeable) -> feat/emerald-v7-original-mixer-binding-census-20261118; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `feat/emerald-visual-playback-lab-20261117` | `d73f42017f` | 2026-11-17 | unique content pending port | 39 new files, 6 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5514 (mergeable) -> feat/emerald-original-animation-audit-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, artifacts/emerald/.gitignore, docs/DRAGON_ATELIER_INSPECTION_LAB.md |
| `feat/emerald-weighted-developmental-evolutions-20261117` | `1dd56e2f97` | 2026-11-20 | unique content pending port | 75 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5542 (mergeable) -> feat/emerald-five-evolution-models-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, artifacts/emerald/.gitignore |
| `feat/faction-governance-50-ballot-policies-20261031` | `2a6cb00ccf` | 2026-11-14 | fully on main | every changed blob already on main |
| `feat/frontier-milestone-10` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/frontier-milestone-11` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/frontier-milestone-12` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/frontier-milestone-13` | `79bcaa2624` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/frontier-milestone-14` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/frontier-milestone-9` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/game-continuity-postepoch-tenfold-20261021` | `a209e15373` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/game-delivery-seven-integrity-20261020` | `8dbaf846fd` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/game-mechanics-50-systems-20261031` | `99d5f08fea` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/game-production-seven-quality-gates-20261020` | `4a4d8bc601` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/gamebuilder-e2e-shirt5-20261031-p1` | `0cce948789` | 2026-11-14 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `feat/gameforge-batch-b039` | `26f867f20e` | 2026-11-14 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `feat/gameforge-conductor` | `b9ab9b5619` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/gameforge-expanded-genre-catalog-20261113` | `1686828700` | 2026-11-16 | unique content pending port | 0 new files, 2 modified files survive a 3-way merge; open PR #5300 (conflicting) -> main |
| `feat/gameforge-materialise-smoke-20261017` | `3315ae3597` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/gf-4122-coder-lead-20261024` | `fc81a4b32f` | 2026-10-24 | fully on main | every changed blob already on main |
| `feat/gf-4167-coder-lead-20261024` | `c226726b20` | 2026-10-24 | unique content pending port | 2 new files, 0 modified files survive a 3-way merge; e.g. artifacts/coder-lead/status-20261024-1847.md, artifacts/coder-lead/status-20261024-1905.md |
| `feat/gf-4167-weather-fps-lod-20261024` | `b27e99ddc0` | 2026-10-24 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. artifacts/coder-lead/status-20261024-1847.md |
| `feat/gf-b-save-restore-replay` | `43d48202e8` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/gf-b020-char-20261024` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/gf-b023-shirt4-20261024` | `def1a10310` | 2026-11-13 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `feat/gf-b024-shirt4-20261024` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/gf-b024-shirt4-20261031` | `cd0a42e7af` | 2026-11-13 | nothing unique | superseded: its 5 remaining edits conflict with newer main versions |
| `feat/gf-b038-oyvind-20261024` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/gf-b040-carrol-20261024` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/gf-b040-coderlead-20261024` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/gf-b040-s4s5-oyvind-20261024` | `19a036717c` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/gf-build-oyvind-20261024` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/gf-c-p0-provider-runtime` | `096123e24d` | 2026-11-14 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `feat/gf-cli-roger-20261024` | `3f50abf90f` | 2026-10-24 | ported in PR #5779 |  |
| `feat/gf-d-shirt1-20261024` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/gf-deployment-nsog-20261024` | `bf667cd3f5` | 2026-11-14 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `feat/gf-f-char-20261024` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/gf-f-frontend-20261024` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/gf-g-jones-20261024` | `847e98435a` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/gf-h-nav-grounding` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/gf-i-art-starlit-20261024` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/gf-j-coder-lead-20261024` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/gf-m-shirt2-20261031` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/gf-n-jenkins-20261024` | `518846c722` | 2026-11-13 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. docs/reconciliation/GAME_FRONTIER_HEAVY_RECOVERY_20261113.md |
| `feat/gf-quiz-bank-bork-20261024` | `db935fc7ae` | 2026-11-14 | fully on main | every changed blob already on main |
| `feat/gf-shard-seal-bork-20261024` | `f6ad1201ec` | 2026-11-14 | fully on main | every changed blob already on main |
| `feat/gfm-qual-harness-carrol-20261031` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/gguf-consumer-competitive-planning-20261116` | `1a4544f95c` | 2026-11-16 | unique content pending port | 75 new files, 22 modified files survive a 3-way merge; open PR #5465 (conflicting) -> main; e.g. docs/ai/GGUF_COMPETITIVE_CONSUMER_PLANNING_2026_11_16.md, scripts/audit_consumer_gguf_shards.py, scripts/benchmark_resident_gguf_holdout.py |
| `feat/gguf-native-topology-tuning-20261116` | `a7dd25a0d6` | 2026-11-16 | unique content pending port | 67 new files, 19 modified files survive a 3-way merge; open PR #5466 (conflicting) -> feat/gguf-consumer-competitive-planning-20261116; e.g. docs/ai/GGUF_COMPETITIVE_CONSUMER_PLANNING_2026_11_16.md, scripts/audit_consumer_gguf_shards.py, scripts/benchmark_resident_gguf_holdout.py |
| `feat/gguf-semantic-native-tuning-wave-20261116` | `68afb1c7fa` | 2026-11-20 | unique content pending port | 75 new files, 22 modified files survive a 3-way merge; open PR #5467 (mergeable) -> feat/gguf-consumer-competitive-planning-20261116; e.g. docs/ai/GGUF_COMPETITIVE_CONSUMER_PLANNING_2026_11_16.md, scripts/audit_consumer_gguf_shards.py, scripts/benchmark_resident_gguf_holdout.py |
| `feat/jeeves-2026-single-host-inference-lease` | `52ebf1802b` | 2026-11-20 | fully on main | every changed blob already on main |
| `feat/jeeves-adaptive-no-found-context-20261019` | `2a6cb00ccf` | 2026-11-14 | fully on main | every changed blob already on main |
| `feat/jeeves-batch-verified-artifact-review-20261104-r70` | `e440045c35` | 2026-11-04 | nothing unique | superseded: its 150 remaining edits conflict with newer main versions |
| `feat/jeeves-book-weights-game-interaction-20261021` | `6420c662af` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/jeeves-cgroup-aware-private-device-telemetry-20261104-r44` | `f3b3ca2324` | 2026-11-04 | nothing unique | superseded: its 152 remaining edits conflict with newer main versions |
| `feat/jeeves-chat-cognition-quality-20261116` | `494301049d` | 2026-11-16 | unique content pending port | 6 new files, 3 modified files survive a 3-way merge; open PR #5469 (conflicting) -> main; e.g. docs/ai/JEEVES_CHAT_COGNITION_QUALITY.md, skeleton/app/jeeves_chat_benchmark.py, skeleton/app/jeeves_chat_cognition.py |
| `feat/jeeves-chat-cognitive-composition-20261116` | `29e8c3e6b9` | 2026-11-20 | unique content pending port | 107 new files, 26 modified files survive a 3-way merge; open PR #5468 (mergeable) -> feat/gguf-consumer-competitive-planning-20261116; e.g. docs/ai/GGUF_COMPETITIVE_CONSUMER_PLANNING_2026_11_16.md, scripts/audit_consumer_gguf_shards.py, scripts/benchmark_resident_gguf_holdout.py |
| `feat/jeeves-chat-context-intelligence-20261116` | `962850e3b8` | 2026-11-20 | unique content pending port | 20 new files, 4 modified files survive a 3-way merge; open PR #5471 (mergeable) -> feat/jeeves-chat-memory-continuity-20261116; e.g. docs/ai/JEEVES_CHAT_ADAPTIVE_CONTEXT_VECTOR_QUALITY.md, docs/ai/JEEVES_CHAT_APPROVED_MEMORY_CONTINUITY.md, docs/ai/JEEVES_CHAT_COGNITION_QUALITY.md |
| `feat/jeeves-chat-deliberation-long-memory-20261116` | `6f415e50ff` | 2026-11-20 | unique content pending port | 27 new files, 5 modified files survive a 3-way merge; open PR #5472 (mergeable) -> feat/jeeves-chat-context-intelligence-20261116; e.g. docs/ai/JEEVES_CHAT_ADAPTIVE_CONTEXT_VECTOR_QUALITY.md, docs/ai/JEEVES_CHAT_APPROVED_MEMORY_CONTINUITY.md, docs/ai/JEEVES_CHAT_COGNITION_QUALITY.md |
| `feat/jeeves-chat-memory-continuity-20261116` | `dda0e9a700` | 2026-11-20 | unique content pending port | 10 new files, 3 modified files survive a 3-way merge; open PR #5470 (mergeable) -> feat/jeeves-chat-cognition-quality-20261116; e.g. docs/ai/JEEVES_CHAT_APPROVED_MEMORY_CONTINUITY.md, docs/ai/JEEVES_CHAT_COGNITION_QUALITY.md, skeleton/app/jeeves_approved_memory.py |
| `feat/jeeves-chat-multimodal-verification-20261116` | `0f0bf84995` | 2026-11-20 | unique content pending port | 35 new files, 5 modified files survive a 3-way merge; open PR #5473 (mergeable) -> feat/jeeves-chat-deliberation-long-memory-20261116; e.g. docs/ai/JEEVES_CHAT_ADAPTIVE_CONTEXT_VECTOR_QUALITY.md, docs/ai/JEEVES_CHAT_APPROVED_MEMORY_CONTINUITY.md, docs/ai/JEEVES_CHAT_COGNITION_QUALITY.md |
| `feat/jeeves-complete-durable-local-workspace-20261113` | `62b54e1983` | 2026-11-14 | unique content pending port | 0 new files, 6 modified files survive a 3-way merge |
| `feat/jeeves-desktop-advanced-planning-20261104-r64` | `07cdd2a509` | 2026-11-05 | nothing unique | superseded: its 150 remaining edits conflict with newer main versions |
| `feat/jeeves-desktop-durable-native-work-orders-20261104-r57` | `2d72760c93` | 2026-11-05 | nothing unique | superseded: its 153 remaining edits conflict with newer main versions |
| `feat/jeeves-desktop-reviewed-existing-file-edits-20261104-r61` | `416e776394` | 2026-11-05 | nothing unique | superseded: its 155 remaining edits conflict with newer main versions |
| `feat/jeeves-desktop-serial-durable-work-batches-20261104-r66` | `f7e3ad7677` | 2026-11-05 | nothing unique | superseded: its 151 remaining edits conflict with newer main versions |
| `feat/jeeves-desktop-signed-source-agent-20261104-r62` | `0e4db428ee` | 2026-11-05 | nothing unique | superseded: its 156 remaining edits conflict with newer main versions |
| `feat/jeeves-desktop-source-search-and-attachments-20261104-r60` | `1524c50ec7` | 2026-11-05 | nothing unique | superseded: its 155 remaining edits conflict with newer main versions |
| `feat/jeeves-desktop-strict-native-agent-20261104-r56` | `94c44f754c` | 2026-11-05 | nothing unique | superseded: its 153 remaining edits conflict with newer main versions |
| `feat/jeeves-director-controls-cinematics-replay-20261016` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/jeeves-director-media-http-e2e-20261016` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/jeeves-dragon-e2e-observation-20261017` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/jeeves-dragon-production-milestones-20261016` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/jeeves-durable-milestones-20261020` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/jeeves-dynamic-worlds-faction-transit-massive-20261016` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/jeeves-exclusive-native-work-lease-20261104-r69` | `e440045c35` | 2026-11-04 | nothing unique | superseded: its 150 remaining edits conflict with newer main versions |
| `feat/jeeves-first-laptop-full-20-domains-20261104` | `fdd612e061` | 2026-11-05 | nothing unique | superseded: its 173 remaining edits conflict with newer main versions |
| `feat/jeeves-first-laptop-gates-core-20261104` | `5e4f356de4` | 2026-11-05 | unique content pending port | 0 new files, 40 modified files survive a 3-way merge |
| `feat/jeeves-first-laptop-host-readiness-summary-20261104` | `9ea3904118` | 2026-11-05 | nothing unique | superseded: its 172 remaining edits conflict with newer main versions |
| `feat/jeeves-first-laptop-runtime-safety-consolidation-20261104` | `6efa8fe242` | 2026-11-05 | nothing unique | superseded: its 173 remaining edits conflict with newer main versions |
| `feat/jeeves-full-runtime-ci-telemetry-integration-20261104-r48` | `17bded6f26` | 2026-11-04 | nothing unique | superseded: its 156 remaining edits conflict with newer main versions |
| `feat/jeeves-game-builder-quality-20261112` | `f54bb0349d` | 2026-11-16 | unique content pending port | 1 new files, 19 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5285 (conflicting) -> main; e.g. tests/test_frontend_setup_vhost_regression.py |
| `feat/jeeves-game-cli-synergy-20261016` | `ba1658174a` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/jeeves-game-e2e-dragon-observation-20261017` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/jeeves-godot-live-bridge-dragon-lab-20261016` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/jeeves-grounded-game-quality-20261113` | `afb6eb5555` | 2026-11-13 | unique content pending port | 0 new files, 10 modified files survive a 3-way merge; 1 paths already carried by port PRs |
| `feat/jeeves-hardware-aware-offline-desktop-20261104-r54` | `175fb3a90b` | 2026-11-05 | nothing unique | superseded: its 152 remaining edits conflict with newer main versions |
| `feat/jeeves-headless-native-sqlite-code-generation-20261105-r79` | `3be2972257` | 2026-11-05 | nothing unique | superseded: its 151 remaining edits conflict with newer main versions |
| `feat/jeeves-headless-offline-source-work-cli-20261104-r77` | `ca47b71d27` | 2026-11-05 | nothing unique | superseded: its 149 remaining edits conflict with newer main versions |
| `feat/jeeves-host-cpu-observation-20261104` | `11ac0af8b5` | 2026-11-05 | nothing unique | superseded: its 173 remaining edits conflict with newer main versions |
| `feat/jeeves-host-filesystem-observation-20261104` | `58165427bf` | 2026-11-05 | nothing unique | superseded: its 173 remaining edits conflict with newer main versions |
| `feat/jeeves-host-memory-observation-20261104` | `74892bc562` | 2026-11-05 | nothing unique | superseded: its 173 remaining edits conflict with newer main versions |
| `feat/jeeves-hyperdispatcher-foundation-20261116` | `0bb1aaf0ab` | 2026-11-16 | unique content pending port | 32 new files, 55 modified files survive a 3-way merge; open PR #5474 (conflicting) -> main; e.g. .github/workflows/jeeves-hyperdispatcher-source.yml, docs/ai/JEEVES_HYPERDISPATCHER_ALTERNATIVE_CAMPAIGN.md, docs/ai/JEEVES_HYPERDISPATCHER_COMPETITIVE_CAMPAIGN.md |
| `feat/jeeves-labyrinth-navigation-canon-audit-20261016` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/jeeves-laptop-cancellation-20261104-source-r8` | `2f2b40a191` | 2026-11-04 | nothing unique | superseded: its 162 remaining edits conflict with newer main versions |
| `feat/jeeves-laptop-cold-restart-20261104-source-r8` | `e1b8bda432` | 2026-11-05 | unique content pending port | 0 new files, 40 modified files survive a 3-way merge |
| `feat/jeeves-laptop-context-window-20261104` | `ec24a25992` | 2026-11-04 | nothing unique | superseded: its 162 remaining edits conflict with newer main versions |
| `feat/jeeves-laptop-context-window-guard-20261104-r2` | `5bddd152cb` | 2026-11-04 | nothing unique | superseded: its 162 remaining edits conflict with newer main versions |
| `feat/jeeves-laptop-cpu-admission-20261104` | `ec24a25992` | 2026-11-04 | nothing unique | superseded: its 162 remaining edits conflict with newer main versions |
| `feat/jeeves-laptop-cpu-admission-20261104-sourcebound-r3` | `d3c1332ff2` | 2026-11-04 | nothing unique | superseded: its 162 remaining edits conflict with newer main versions |
| `feat/jeeves-laptop-first-turn-20261104-contract-r9` | `877f432fbd` | 2026-11-04 | nothing unique | superseded: its 162 remaining edits conflict with newer main versions |
| `feat/jeeves-laptop-generation-budget-20261104-strict-r6` | `dc5ea1e8c6` | 2026-11-05 | unique content pending port | 0 new files, 40 modified files survive a 3-way merge |
| `feat/jeeves-laptop-gpu-admission-20261104` | `ec24a25992` | 2026-11-04 | nothing unique | superseded: its 162 remaining edits conflict with newer main versions |
| `feat/jeeves-laptop-gpu-admission-20261104-sourcebound-r3` | `090a73a11d` | 2026-11-05 | unique content pending port | 0 new files, 40 modified files survive a 3-way merge |
| `feat/jeeves-laptop-memory-capacity-20261104` | `7d12834bf7` | 2026-11-04 | nothing unique | superseded: its 162 remaining edits conflict with newer main versions |
| `feat/jeeves-laptop-memory-consent-20261104-guard-r7` | `7cf0f8481c` | 2026-11-05 | unique content pending port | 0 new files, 40 modified files survive a 3-way merge |
| `feat/jeeves-laptop-memory-consent-20261104-source-r5` | `ec24a25992` | 2026-11-04 | nothing unique | superseded: its 162 remaining edits conflict with newer main versions |
| `feat/jeeves-laptop-model-manifest-20261104` | `328c09da38` | 2026-11-05 | unique content pending port | 0 new files, 40 modified files survive a 3-way merge |
| `feat/jeeves-laptop-native-session-20261104` | `ec24a25992` | 2026-11-04 | nothing unique | superseded: its 162 remaining edits conflict with newer main versions |
| `feat/jeeves-laptop-native-session-20261104-sourcebound-r3` | `ee9fdc43d5` | 2026-11-04 | nothing unique | superseded: its 162 remaining edits conflict with newer main versions |
| `feat/jeeves-laptop-ops-cpu-admission-20261104` | `ec24a25992` | 2026-11-04 | nothing unique | superseded: its 162 remaining edits conflict with newer main versions |
| `feat/jeeves-laptop-ops-gpu-admission-20261104` | `ec24a25992` | 2026-11-04 | nothing unique | superseded: its 162 remaining edits conflict with newer main versions |
| `feat/jeeves-laptop-ops-memory-capacity-20261104` | `ec24a25992` | 2026-11-04 | nothing unique | superseded: its 162 remaining edits conflict with newer main versions |
| `feat/jeeves-laptop-ops-model-manifest-20261104` | `ec24a25992` | 2026-11-04 | nothing unique | superseded: its 162 remaining edits conflict with newer main versions |
| `feat/jeeves-laptop-ops-tokenizer-identity-20261104` | `ec24a25992` | 2026-11-04 | nothing unique | superseded: its 162 remaining edits conflict with newer main versions |
| `feat/jeeves-laptop-output-receipt-20261104-sourcebound-r3` | `58a0cfaff3` | 2026-11-05 | unique content pending port | 0 new files, 40 modified files survive a 3-way merge |
| `feat/jeeves-laptop-pressure-recovery-20261104-guard-r7` | `e69ef9f7a1` | 2026-11-04 | nothing unique | superseded: its 162 remaining edits conflict with newer main versions |
| `feat/jeeves-laptop-pressure-recovery-20261104-source-r5` | `ec24a25992` | 2026-11-04 | nothing unique | superseded: its 162 remaining edits conflict with newer main versions |
| `feat/jeeves-laptop-release-proof-holds-20261104-r10` | `80b362a140` | 2026-11-04 | nothing unique | superseded: its 162 remaining edits conflict with newer main versions |
| `feat/jeeves-laptop-signed-sources-20261104-matrix-r4` | `00d0769bce` | 2026-11-04 | nothing unique | superseded: its 162 remaining edits conflict with newer main versions |
| `feat/jeeves-laptop-source-retrieval-20261104-strict-r6` | `87b2d04f3b` | 2026-11-05 | unique content pending port | 0 new files, 40 modified files survive a 3-way merge |
| `feat/jeeves-laptop-sqlite-replay-20261104-strict-r6` | `8348a67388` | 2026-11-04 | nothing unique | superseded: its 162 remaining edits conflict with newer main versions |
| `feat/jeeves-laptop-tokenizer-identity-20261104` | `ec24a25992` | 2026-11-04 | nothing unique | superseded: its 162 remaining edits conflict with newer main versions |
| `feat/jeeves-laptop-tool-grants-20261104-guard-r7` | `1700b5d018` | 2026-11-04 | nothing unique | superseded: its 162 remaining edits conflict with newer main versions |
| `feat/jeeves-laptop-tool-grants-20261104-source-r5` | `ec24a25992` | 2026-11-04 | nothing unique | superseded: its 162 remaining edits conflict with newer main versions |
| `feat/jeeves-live-preload-hardware-admission-20261104-r68` | `c81730315d` | 2026-11-05 | nothing unique | superseded: its 148 remaining edits conflict with newer main versions |
| `feat/jeeves-living-npcs-economy-20261016` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/jeeves-measured-local-efficiency-20261116` | `67b20a0f32` | 2026-11-16 | unique content pending port | 44 new files, 26 modified files survive a 3-way merge; open PR #5464 (conflicting) -> main; e.g. docs/ai/JEEVES_ADAPTIVE_LOCAL_INTELLIGENCE.md, docs/ai/JEEVES_ADVANCED_ADAPTATION_VI.md, docs/ai/JEEVES_CAUSAL_EFFICIENCY_X.md |
| `feat/jeeves-model-inventory-reconcile-20261016` | `7d09b0c2db` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/jeeves-native-builder-workspace-20261113` | `c6b307f3f1` | 2026-11-13 | unique content pending port | 0 new files, 10 modified files survive a 3-way merge; 1 paths already carried by port PRs |
| `feat/jeeves-native-campaign-desktop-20261105-r88` | `03fc812311` | 2026-11-13 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `feat/jeeves-native-campaign-goal-composer-20261105-r89` | `973f9dfef5` | 2026-11-14 | fully on main | every changed blob already on main |
| `feat/jeeves-native-campaign-source-assembly-20261105-r87` | `03fc812311` | 2026-11-13 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `feat/jeeves-native-desktop-pressure-supervisor-20261104-r63` | `a18d4d59ee` | 2026-11-05 | nothing unique | superseded: its 156 remaining edits conflict with newer main versions |
| `feat/jeeves-native-mixed-project-work-package-20261104-r75` | `4b67f97742` | 2026-11-05 | nothing unique | superseded: its 155 remaining edits conflict with newer main versions |
| `feat/jeeves-native-operational-bridge-20261103` | `d678c43757` | 2026-11-05 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `feat/jeeves-native-private-source-proposal-escrow-20261105-r80` | `21e7f7c71d` | 2026-11-05 | nothing unique | superseded: its 149 remaining edits conflict with newer main versions |
| `feat/jeeves-native-source-campaign-20261105-r86` | `ef4f3837cc` | 2026-11-05 | nothing unique | superseded: its 148 remaining edits conflict with newer main versions |
| `feat/jeeves-native-source-draft-repair-loop-20261104-r72` | `01fe6de66a` | 2026-11-05 | nothing unique | superseded: its 155 remaining edits conflict with newer main versions |
| `feat/jeeves-native-source-escrow-to-private-stage-20261105-r82` | `9971323565` | 2026-11-05 | nothing unique | superseded: its 150 remaining edits conflict with newer main versions |
| `feat/jeeves-native-verified-project-source-context-20261104-r73` | `b19592e31a` | 2026-11-05 | nothing unique | superseded: its 153 remaining edits conflict with newer main versions |
| `feat/jeeves-offline-capsule-transport-20261105-r85` | `3622bbf840` | 2026-11-05 | nothing unique | superseded: its 148 remaining edits conflict with newer main versions |
| `feat/jeeves-offline-conflict-aware-source-reconciliation-20261104-r71` | `7127dcd15d` | 2026-11-05 | nothing unique | superseded: its 153 remaining edits conflict with newer main versions |
| `feat/jeeves-offline-desktop-native-workbench-20261104-r52` | `d53f88bb89` | 2026-11-05 | nothing unique | superseded: its 154 remaining edits conflict with newer main versions |
| `feat/jeeves-offline-python-source-graph-20261104-r78` | `4c8c35ee9c` | 2026-11-05 | nothing unique | superseded: its 149 remaining edits conflict with newer main versions |
| `feat/jeeves-offline-reviewed-git-patch-delivery-20261104-r69` | `13765ae5d6` | 2026-11-05 | nothing unique | superseded: its 150 remaining edits conflict with newer main versions |
| `feat/jeeves-offline-verified-static-source-gates-20261104-r70` | `e4d141d6dc` | 2026-11-05 | nothing unique | superseded: its 149 remaining edits conflict with newer main versions |
| `feat/jeeves-operator-readonly-laptop-probe-cli-20261104` | `76566ee705` | 2026-11-05 | nothing unique | superseded: its 172 remaining edits conflict with newer main versions |
| `feat/jeeves-operator-wall-disclosure-custody-20261104-r36` | `1fa23e068f` | 2026-11-05 | nothing unique | superseded: its 158 remaining edits conflict with newer main versions |
| `feat/jeeves-operator-workspace-source-delivery-20261104-r53` | `a32d955da9` | 2026-11-05 | nothing unique | superseded: its 154 remaining edits conflict with newer main versions |
| `feat/jeeves-ops-tokenizer-identity-20261104-b` | `63a4ce5a8d` | 2026-11-05 | unique content pending port | 0 new files, 40 modified files survive a 3-way merge |
| `feat/jeeves-private-durable-batch-recovery-20261104-r67` | `815f0cac04` | 2026-11-05 | nothing unique | superseded: its 145 remaining edits conflict with newer main versions |
| `feat/jeeves-private-full-source-capsule-20261105-r83` | `d11365a8e1` | 2026-11-05 | nothing unique | superseded: its 149 remaining edits conflict with newer main versions |
| `feat/jeeves-private-source-overlay-staging-20261104-r76` | `83a4f4681d` | 2026-11-05 | nothing unique | superseded: its 158 remaining edits conflict with newer main versions |
| `feat/jeeves-readonly-gguf-header-observation-20261104` | `c6e80d42ec` | 2026-11-05 | nothing unique | superseded: its 173 remaining edits conflict with newer main versions |
| `feat/jeeves-repl-finite-output-custody-20261104-r40` | `8d250fc57b` | 2026-11-05 | nothing unique | superseded: its 154 remaining edits conflict with newer main versions |
| `feat/jeeves-rootless-offline-source-test-20261104-r79` | `7bb6f5502c` | 2026-11-04 | nothing unique | superseded: its 149 remaining edits conflict with newer main versions |
| `feat/jeeves-serial-native-source-build-wave-20261104-r76` | `8e89319d09` | 2026-11-04 | nothing unique | superseded: its 153 remaining edits conflict with newer main versions |
| `feat/jeeves-society-inventory-integrity-20261017` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/jeeves-verified-selected-project-import-closure-20261105-r84` | `f20cf3fa05` | 2026-11-05 | nothing unique | superseded: its 148 remaining edits conflict with newer main versions |
| `feat/jones-B071-B072-replay-perf-gates` | `ed2e1ca22d` | 2026-10-24 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `feat/laptop-gguf-cold-reopen-sqlite-acceptance-20261104-r22` | `7e990b5674` | 2026-11-05 | nothing unique | superseded: its 174 remaining edits conflict with newer main versions |
| `feat/laptop-real-first-turn-source-approved-acceptance-20261104-r14` | `f86e7b94d1` | 2026-11-05 | nothing unique | superseded: its 175 remaining edits conflict with newer main versions |
| `feat/local-ai-approved-real-first-turn-20261104` | `1e71eaf712` | 2026-11-04 | unique content pending port | 3 new files, 0 modified files survive a 3-way merge; e.g. skeleton/testing/test_jeeves_operator_postio_epoch_start.py, skeleton/testing/test_jeeves_operator_postio_failure_custody.py, skeleton/testing/test_jeeves_operator_postio_private_replay.py |
| `feat/local-ai-live-source-fenced-laptop-cli-20261104-r47` | `305d60e5c3` | 2026-11-05 | nothing unique | superseded: its 148 remaining edits conflict with newer main versions |
| `feat/market-exchanges-50-commodities-20261031` | `5e1cced1f6` | 2026-11-05 | fully on main | every changed blob already on main |
| `feat/mb-ai-builder-edit-oystein-20261031` | `57626b79ff` | 2026-11-05 | nothing unique | superseded: its 27 remaining edits conflict with newer main versions |
| `feat/mb-ai-builder-engine-oystein-20261031` | `113f9e7cff` | 2026-11-05 | nothing unique | superseded: its 17 remaining edits conflict with newer main versions |
| `feat/mb-ai-builder-validate-oystein-20261031` | `bce0f7f9ed` | 2026-11-05 | nothing unique | superseded: its 19 remaining edits conflict with newer main versions |
| `feat/mb-api-docs-jenkins-20261031` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/mb-api-v1-middleware-20261031` | `be55993880` | 2026-11-03 | nothing unique | superseded: its 10 remaining edits conflict with newer main versions |
| `feat/mb-arch-docs-jenkins-20261031` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/mb-asset-import-oyvind-20261031` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/mb-b025-gameplay-state-migration-willy-20261031` | `326139b217` | 2026-11-05 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `feat/mb-b031-b040-oyvind-20261031` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/mb-b071-b080-oystein-20261031` | `5b61c7fb70` | 2026-11-05 | fully on main | every changed blob already on main |
| `feat/mb-b081-b100-orjan-20261031` | `7286828803` | 2026-11-05 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `feat/mb-b091-b100-oyvind-20261031` | `12b86d476b` | 2026-11-05 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `feat/mb-backend-core-backend-20261031` | `d3013176b7` | 2026-11-05 | unique content pending port | 19 new files, 3 modified files survive a 3-way merge; e.g. backend/core/core_v1/delivery_ops.py, backend/core/core_v1/envelope.py, backend/core/core_v1/keys.py |
| `feat/mb-build-deploy-devops-20261031` | `9c143aa746` | 2026-11-05 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. skeleton/testing/test_delivery_path_controls.py |
| `feat/mb-core-mount-middleware-20261031` | `2afcba8eeb` | 2026-11-05 | unique content pending port | 8 new files, 3 modified files survive a 3-way merge; e.g. skeleton/gate_plane/core_mount.py, tests/api_v1_edge/test_idempotency_capacity.py, tests/api_v1_edge/test_quota_capacity.py |
| `feat/mb-core-webhook-crypto-backend-20261031` | `c3e5fd415c` | 2026-11-05 | unique content pending port | 19 new files, 3 modified files survive a 3-way merge; e.g. backend/core/core_v1/delivery_ops.py, backend/core/core_v1/envelope.py, backend/core/core_v1/keys.py |
| `feat/mb-economy-murash-20261031` | `246f7a00e7` | 2026-11-05 | fully on main | every changed blob already on main |
| `feat/mb-gf-l-route-repair-middleware-20261031` | `0dde647f3e` | 2026-11-14 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `feat/mb-gfa-wiring-internal-systems-20261031` | `98dc22f996` | 2026-11-13 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `feat/mb-godot-export-shirt1-20261031` | `ee5c210066` | 2026-11-05 | nothing unique | superseded: its 9 remaining edits conflict with newer main versions |
| `feat/mb-hooks-wire-middleware-20261031` | `ff8db1ab4a` | 2026-11-05 | unique content pending port | 8 new files, 3 modified files survive a 3-way merge; e.g. skeleton/gate_plane/core_mount.py, tests/api_v1_edge/test_idempotency_capacity.py, tests/api_v1_edge/test_quota_capacity.py |
| `feat/mb-industry-murash-20261031` | `d0511738d5` | 2026-11-05 | nothing unique | superseded: its 7 remaining edits conflict with newer main versions |
| `feat/mb-localization-oyvind-20261031` | `f5423d1baa` | 2026-11-05 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `feat/mb-mod-api-oyvind-20261031` | `56714841b3` | 2026-11-05 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `feat/mb-perf-profiler-jones-20261031` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/mb-player-analytics-oyvind-20261031` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/mb-player-market-murash-20261031` | `95d7a05485` | 2026-11-05 | nothing unique | superseded: its 7 remaining edits conflict with newer main versions |
| `feat/mb-procgen-oystein-20261031` | `98e76655d8` | 2026-11-03 | nothing unique | superseded: its 27 remaining edits conflict with newer main versions |
| `feat/mb-project-bundle-oyvind-20261031` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/mb-quest-system-oyvind-20261031` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/mb-recovered-systems-edge-middleware-20261114` | `2d406b2b9b` | 2026-11-14 | unique content pending port | 14 new files, 0 modified files survive a 3-way merge; e.g. skeleton/gate_plane/systems/__init__.py, skeleton/gate_plane/systems/bulkhead.py, skeleton/gate_plane/systems/catalog.py |
| `feat/mb-s2s-auth-middleware-20261031` | `6884c56a61` | 2026-11-05 | unique content pending port | 0 new files, 2 modified files survive a 3-way merge |
| `feat/mb-seal-v2-binding-internal-systems-20261031` | `c40c959dba` | 2026-11-05 | unique content pending port | 2 new files, 0 modified files survive a 3-way merge; e.g. skeleton/api/nonce_store.py, tests/test_request_seal_v3_binding.py |
| `feat/mb-seal-v2-internal-systems-20261031` | `b9fe875b7c` | 2026-11-05 | unique content pending port | 2 new files, 0 modified files survive a 3-way merge; e.g. skeleton/api/nonce_store.py, tests/test_request_seal_v3_binding.py |
| `feat/native-candidate-intake-20261103-r1` | `181a1cf06c` | 2026-11-05 | nothing unique | superseded: its 51 remaining edits conflict with newer main versions |
| `feat/native-candidate-integral-assurance-20261103` | `09242d6a46` | 2026-11-03 | nothing unique | superseded: its 50 remaining edits conflict with newer main versions |
| `feat/npc-behaviors-50-role-directors-20261031` | `afc09d2dcd` | 2026-11-05 | fully on main | every changed blob already on main |
| `feat/offline-original-turn-session-r11` | `af893a3aef` | 2026-10-31 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `feat/orjan-b021-deterministic-session-20261114` | `c786c1e899` | 2026-11-14 | ported in PR #5779 |  |
| `feat/orjan-eight-playable-loops-20261114` | `8a1ff3e5c1` | 2026-11-14 | unique content pending port | 1 new files, 2 modified files survive a 3-way merge; e.g. skeleton/testing/test_playable_dual_contract_unification.py |
| `feat/orjan-gameforge-7step-serving-20261114` | `3acc7d6898` | 2026-11-14 | ported in PR #5779 |  |
| `feat/orjan-jeeves-game-builder-20261114` | `78f47b182f` | 2026-11-14 | unique content pending port | 1 new files, 13 modified files survive a 3-way merge; 1 paths already carried by port PRs; e.g. tests/test_game_builder_playable_library_dedup.py |
| `feat/oyvind-sandbox-guarded-exec-fuzz-20261003` | `0668fc64c3` | 2026-10-25 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `feat/plot-beats` | `d4f5364af7` | 2026-11-20 | unique content pending port | 4 new files, 23 modified files survive a 3-way merge; open PR #5694 (mergeable) -> main; e.g. docs/creation/PLOT_BEATS.md, skeleton/ai/agents/jeeves/plot_beats.py, skeleton/ai/forge/media_depth/__init__.py |
| `feat/product-unified-capabilities-20261016` | `94ed519da3` | 2026-10-16 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. .github/workflows/product-ui-local-ai-qualification.yml |
| `feat/production-pipelines-50-recipes-20261031` | `465fe86145` | 2026-11-05 | fully on main | every changed blob already on main |
| `feat/production-planning-depth` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/questflows-50-director-systems-20261031` | `89c479aab4` | 2026-11-05 | fully on main | every changed blob already on main |
| `feat/recover-gf-l-route-repair-middleware-20261114` | `f0df84456d` | 2026-11-14 | fully on main | every changed blob already on main |
| `feat/recover-hooks-wire-core-mount-middleware-20261114` | `cdab7e74ce` | 2026-11-14 | unique content pending port | 8 new files, 4 modified files survive a 3-way merge; e.g. skeleton/gate_plane/core_mount.py, tests/api_v1_edge/test_idempotency_capacity.py, tests/api_v1_edge/test_quota_capacity.py |
| `feat/recover-s2s-canonical-scope-middleware-20261114` | `ccb2029125` | 2026-11-14 | unique content pending port | 0 new files, 5 modified files survive a 3-way merge |
| `feat/recover-v1-edge-body-frames-middleware-20261114` | `b6aac41f72` | 2026-11-14 | unique content pending port | 0 new files, 2 modified files survive a 3-way merge |
| `feat/route-planners-50-world-navigation-20261031` | `31f4ec81ac` | 2026-11-05 | fully on main | every changed blob already on main |
| `feat/sealed-context-sandwich-v1-20261027` | `b7d8518d78` | 2026-10-28 | unique content pending port | 0 new files, 28 modified files survive a 3-way merge |
| `feat/sota-techstack-push-20261029` | `735d18bd35` | 2026-10-30 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `feat/story-arc` | `b6ccaa202b` | 2026-11-19 | unique content pending port | 2 new files, 0 modified files survive a 3-way merge; open PR #5692 (mergeable) -> main; e.g. docs/creation/STORY_ARC.md, skeleton/ai/agents/jeeves/story_arc.py |
| `feat/studio-a-catalog-snapshot-20261031-r11` | `e0809d0bb3` | 2026-11-02 | ported in PR #5767 |  |
| `feat/studio-a-iterative-scene-graph-validation-20261108-r3` | `9b65f0ae0b` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/studio-a-playable-save-restore-20261107-r03` | `a8f9bbfa6a` | 2026-11-09 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. skeleton/testing/test_jeeves_browser_save.py |
| `feat/studio-a-review-atomic-20261107-r01` | `65147db495` | 2026-11-13 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `feat/studio-a-review-replay-fence-20261107-r03` | `3ee9851438` | 2026-11-14 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `feat/studio-a-stale-review-recovery-20261107-r02` | `7c9e89a101` | 2026-11-13 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `feat/studio-a-typed-canon-transaction-20261102-r11` | `11ec3a3ec0` | 2026-11-05 | ported in PR #5779 | all 0 new / 1 modified surviving paths are carried by the port |
| `feat/studio-a-walk-operator-20261031` | `28f657ad74` | 2026-10-31 | ported in PR #5767 | all 93 new / 2 modified surviving paths are carried by the port (21 test modules held: fail on source branch too) |
| `feat/studio-a-world-identity-fence-20261109-r11` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/studio-a-world-state-liveness-20261107-r01` | `c2f805d8e2` | 2026-11-11 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `feat/studio-adaptive-batch-admission-20261030` | `d8e74e437f` | 2026-10-30 | ported in PR #5767 | all 10 new / 0 modified surviving paths are carried by the port |
| `feat/studio-adaptive-multiproject-media-batch-20261030` | `299a110c94` | 2026-10-30 | ported in PR #5767 | all 49 new / 0 modified surviving paths are carried by the port (5 test modules held: fail on source branch too) |
| `feat/studio-art-production-jobs-20261030` | `370d1334d5` | 2026-10-30 | ported in PR #5767 | all 21 new / 0 modified surviving paths are carried by the port |
| `feat/studio-atomic-story-turn-20261030` | `fc04bd518a` | 2026-10-30 | ported in PR #5767 | all 15 new / 0 modified surviving paths are carried by the port |
| `feat/studio-audited-state-replay-20261030` | `cf664b6c08` | 2026-10-30 | ported in PR #5767 | all 34 new / 0 modified surviving paths are carried by the port (1 test modules held: fail on source branch too) |
| `feat/studio-authoritative-2d-physics-replay-20261030` | `64f3509692` | 2026-10-30 | ported in PR #5767 | all 63 new / 0 modified surviving paths are carried by the port (13 test modules held: fail on source branch too) |
| `feat/studio-authoritative-browser-replay-20261030` | `291a27a662` | 2026-10-30 | ported in PR #5767 | all 55 new / 0 modified surviving paths are carried by the port (7 test modules held: fail on source branch too) |
| `feat/studio-authoritative-health-aware-physics-review-20261030` | `089da041cc` | 2026-10-30 | ported in PR #5767 | all 68 new / 0 modified surviving paths are carried by the port (15 test modules held: fail on source branch too) |
| `feat/studio-b-atomic-crafting-economy-20261031-r11` | `bc34252dd4` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/studio-b-bounded-input-collision-20261108-r03` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/studio-b-cinder-ridge-rescue-20261103-r11` | `5459dbf769` | 2026-11-07 | fully on main | every changed blob already on main |
| `feat/studio-b-combat-campaign-author-20261101-r11` | `a655f94e02` | 2026-11-01 | nothing unique | superseded: its 5 remaining edits conflict with newer main versions |
| `feat/studio-b-deterministic-input-routing-20261031-0916` | `edabffb076` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/studio-b-expedition-ledger-49-chapters-20261101` | `e617a23a87` | 2026-11-05 | fully on main | every changed blob already on main |
| `feat/studio-b-fixed-tick-clock-20261108-v6` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/studio-b-godot-export-artifact-custody-20261108` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/studio-b-grid-input-adapter-20261109-r03` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/studio-b-grid-reachable-goal-20261108-r04` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/studio-b-harbor-crafting-20261102-r11` | `64ecb3f96d` | 2026-11-05 | nothing unique | superseded: its 11 remaining edits conflict with newer main versions |
| `feat/studio-b-offline-grid-campaign-20261031-0916` | `87fdf977e9` | 2026-11-05 | nothing unique | superseded: its 33 remaining edits conflict with newer main versions |
| `feat/studio-b-offline-npc-schedule-replay-20261031-r11` | `3865a777f0` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/studio-b-original-pcm-synthesis-20261031-0916` | `db99a9d563` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/studio-b-playable-capsule-sessions-20261031` | `be1f76edea` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/studio-b-player-combat-decision-board-20261102-r11` | `d7d0d966bf` | 2026-11-02 | nothing unique | superseded: its 14 remaining edits conflict with newer main versions |
| `feat/studio-b-portable-byte-boundary-20261107-r11` | `2ef936f785` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/studio-b-quest-transaction-replay-20261031-r11` | `8c47825681` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/studio-b-scene-market-delivery-20261102-r11` | `240eb842e7` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/studio-b-scene-travel-replay-20261031-r11` | `7e5601fbf3` | 2026-11-05 | nothing unique | superseded: its 15 remaining edits conflict with newer main versions |
| `feat/studio-b-scene-weather-travel-20261101-r11` | `56e3370ab7` | 2026-11-01 | nothing unique | superseded: its 10 remaining edits conflict with newer main versions |
| `feat/studio-b-source-bound-turn-combat-20261031-r11` | `2792ea1a28` | 2026-11-05 | unique content pending port | 0 new files, 300 modified files survive a 3-way merge; 2 paths already carried by port PRs |
| `feat/studio-b-verified-godot-export-20261108-0616` | `4a8b236fc7` | 2026-11-14 | unique content pending port | 0 new files, 2 modified files survive a 3-way merge |
| `feat/studio-b-verified-offline-game-package-20261031-0916` | `2acbe4dc29` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/studio-batch-interactive-game-package-20261030` | `56be306868` | 2026-10-30 | ported in PR #5767 | all 55 new / 0 modified surviving paths are carried by the port (7 test modules held: fail on source branch too) |
| `feat/studio-browser-npc-contact-transcripts-20261030` | `7ba1f90589` | 2026-10-30 | ported in PR #5767 | all 71 new / 0 modified surviving paths are carried by the port (18 test modules held: fail on source branch too) |
| `feat/studio-browser-quest-director-20261030` | `c0c395f555` | 2026-10-30 | ported in PR #5767 | all 54 new / 0 modified surviving paths are carried by the port (6 test modules held: fail on source branch too) |
| `feat/studio-browser-quest-replay-operator-cli-20261030` | `e02bac33d2` | 2026-10-30 | ported in PR #5767 | all 61 new / 0 modified surviving paths are carried by the port (11 test modules held: fail on source branch too) |
| `feat/studio-c-atomic-stream-admission-20261031` | `74472d9739` | 2026-11-05 | unique content pending port | 16 new files, 6 modified files survive a 3-way merge; 1 paths already carried by port PRs; e.g. docs/ai/KV_INDEPENDENT_ROLLBACK_ANCHOR.md, docs/ai/KV_LIVE_TIER_CONTROLLER.md, docs/ai/KV_MIGRATION_JOURNAL.md |
| `feat/studio-c-compose-guarded-activation-20261103` | `8645ad4068` | 2026-11-07 | unique content pending port | 4 new files, 1 modified files survive a 3-way merge; e.g. docs/ai/COMPOSE_GUARDED_ACTIVATION_2026_11_03.md, docs/ai/COMPOSE_GUARDED_DATABASE_ALIGNMENT_2026_11_03.md, skeleton/testing/test_mongo_epoch_live_replica.py |
| `feat/studio-c-cpu-kv-durable-spill-20261031-r06` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/studio-c-encrypted-offline-spill-20261031-r06` | `7dabaae56d` | 2026-11-05 | unique content pending port | 20 new files, 6 modified files survive a 3-way merge; 1 paths already carried by port PRs; e.g. docs/ai/KV_INDEPENDENT_ROLLBACK_ANCHOR.md, docs/ai/KV_LIVE_TIER_CONTROLLER.md, docs/ai/KV_MIGRATION_JOURNAL.md |
| `feat/studio-c-energy-hysteresis-20261031-r06` | `8d35aabce7` | 2026-11-14 | fully on main | every changed blob already on main |
| `feat/studio-c-fair-stream-custody-20261031-r09` | `6cec32bcba` | 2026-11-01 | unique content pending port | 1 new files, 3 modified files survive a 3-way merge; 1 paths already carried by port PRs; e.g. tests/test_app_offline_reclaim_pressure.py |
| `feat/studio-c-gguf-header-preflight-20261108-r3` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/studio-c-kv-pressure-reclamation-20261031-r05` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/studio-c-kv-tier-pressure-planner-20261031-r07` | `525b1da48f` | 2026-11-05 | unique content pending port | 15 new files, 3 modified files survive a 3-way merge; 1 paths already carried by port PRs; e.g. docs/ai/KV_INDEPENDENT_ROLLBACK_ANCHOR.md, docs/ai/KV_LIVE_TIER_CONTROLLER.md, docs/ai/KV_MIGRATION_JOURNAL.md |
| `feat/studio-c-linux-psi-pressure-20261031-r05` | `02e6b4ab37` | 2026-11-05 | unique content pending port | 3 new files, 0 modified files survive a 3-way merge; e.g. docs/ai/LOCAL_RESOURCE_MONITOR.md, skeleton/ai/runtime/inference/resource_monitor.py, skeleton/testing/test_local_resource_monitor.py |
| `feat/studio-c-local-resource-monitor-20261031-r05` | `9ba295a479` | 2026-11-05 | unique content pending port | 3 new files, 0 modified files survive a 3-way merge; e.g. docs/ai/LOCAL_RESOURCE_MONITOR.md, skeleton/ai/runtime/inference/resource_monitor.py, skeleton/testing/test_local_resource_monitor.py |
| `feat/studio-c-long-context-spool-20261031-r06` | `4fe9ea537b` | 2026-11-05 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `feat/studio-c-native-nvml-memory-probe-20261031-r05` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/studio-c-offline-cpu-topology-budget-20261031-r06` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/studio-c-offline-energy-admission-20261031-r06` | `7bf40255dc` | 2026-11-13 | fully on main | every changed blob already on main |
| `feat/studio-c-offline-weight-inventory-20261031-r05` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/studio-c-pressure-aware-iteration-scheduler-20261031-r05` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feat/studio-c-reclaim-psi-20261031-r08` | `59ab1c35f7` | 2026-11-05 | unique content pending port | 1 new files, 3 modified files survive a 3-way merge; 1 paths already carried by port PRs; e.g. tests/test_app_offline_reclaim_pressure.py |
| `feat/studio-c-sealed-readonly-weight-pages-20261031-r05` | `f9cf1b690b` | 2026-11-02 | fully on main | every changed blob already on main |
| `feat/studio-c-tail-latency-qualification-20261031-r09` | `85d2fa89f5` | 2026-11-05 | unique content pending port | 1 new files, 3 modified files survive a 3-way merge; 1 paths already carried by port PRs; e.g. tests/test_app_offline_reclaim_pressure.py |
| `feat/studio-canonical-quest-save-20261030` | `d1246ecb88` | 2026-10-30 | ported in PR #5767 | all 17 new / 0 modified surviving paths are carried by the port |
| `feat/studio-catalog-cohort-01-20261031` | `68b3f9878d` | 2026-11-05 | unique content pending port | 21 new files, 7 modified files survive a 3-way merge; 1 paths already carried by port PRs; e.g. docs/ai/KV_INDEPENDENT_ROLLBACK_ANCHOR.md, docs/ai/KV_LIVE_TIER_CONTROLLER.md, docs/ai/KV_MIGRATION_JOURNAL.md |
| `feat/studio-catalog-cohort-02-20261031` | `2897ab6934` | 2026-11-05 | unique content pending port | 21 new files, 7 modified files survive a 3-way merge; 1 paths already carried by port PRs; e.g. docs/ai/KV_INDEPENDENT_ROLLBACK_ANCHOR.md, docs/ai/KV_LIVE_TIER_CONTROLLER.md, docs/ai/KV_MIGRATION_JOURNAL.md |
| `feat/studio-catalog-cohort-03-20261031` | `6df4010336` | 2026-11-05 | ported in PR #5767 | all 0 new / 1 modified surviving paths are carried by the port |
| `feat/studio-catalog-cohort-04-20261031` | `e3e70aeb22` | 2026-11-05 | ported in PR #5767 | all 0 new / 1 modified surviving paths are carried by the port |
| `feat/studio-catalog-cohort-05-20261031` | `478cb8c48d` | 2026-11-05 | ported in PR #5767 | all 0 new / 1 modified surviving paths are carried by the port |
| `feat/studio-catalog-cohort-06-20261031` | `990591fb0b` | 2026-11-05 | ported in PR #5767 | all 0 new / 1 modified surviving paths are carried by the port |
| `feat/studio-catalog-cohort-07-20261031` | `9262cd258e` | 2026-11-05 | ported in PR #5767 | all 0 new / 1 modified surviving paths are carried by the port |
| `feat/studio-catalog-cohort-08-20261031` | `7ddff60ebb` | 2026-11-05 | ported in PR #5767 | all 0 new / 1 modified surviving paths are carried by the port |
| `feat/studio-catalog-cohort-09-20261031` | `2e255faf74` | 2026-11-05 | ported in PR #5767 | all 0 new / 1 modified surviving paths are carried by the port |
| `feat/studio-catalog-cohort-10-20261031` | `54b6fd83ab` | 2026-11-05 | ported in PR #5767 | all 0 new / 1 modified surviving paths are carried by the port |
| `feat/studio-catalog-cohort-11-20261031` | `f96c1be9cf` | 2026-11-05 | ported in PR #5767 | all 0 new / 1 modified surviving paths are carried by the port |
| `feat/studio-catalog-cohort-12-20261031` | `edbb3856d3` | 2026-11-05 | ported in PR #5767 | all 0 new / 1 modified surviving paths are carried by the port |
| `feat/studio-catalog-cohort-13-20261031` | `d344c0dd48` | 2026-11-05 | ported in PR #5767 | all 0 new / 1 modified surviving paths are carried by the port |
| `feat/studio-catalog-cohort-14-20261031` | `8d81dc0cac` | 2026-11-05 | ported in PR #5767 | all 0 new / 1 modified surviving paths are carried by the port |
| `feat/studio-catalog-cohort-15-20261031` | `7ac6f5f398` | 2026-11-05 | ported in PR #5767 | all 0 new / 1 modified surviving paths are carried by the port |
| `feat/studio-catalog-cohort-16-20261031` | `8fbc6600a1` | 2026-11-05 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; 74 paths already carried by port PRs; e.g. tests/test_studio_ecosystem_catalog_fd_security.py |
| `feat/studio-catalog-integration-20261031` | `f5e0379daf` | 2026-11-01 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; 74 paths already carried by port PRs; e.g. tests/test_studio_ecosystem_catalog_fd_security.py |
| `feat/studio-catalog-semantic-discovery-20261030` | `15a8b4fa38` | 2026-10-30 | ported in PR #5767 | all 7 new / 0 modified surviving paths are carried by the port |
| `feat/studio-complete-bundle-verification-20261030` | `19455cfb51` | 2026-10-30 | ported in PR #5767 | all 47 new / 0 modified surviving paths are carried by the port (4 test modules held: fail on source branch too) |
| `feat/studio-cross-section-continuity-20261030` | `4144ec06f5` | 2026-10-30 | ported in PR #5767 | all 7 new / 0 modified surviving paths are carried by the port |
| `feat/studio-d-app-first-playable-journey-20261031-r11` | `8cff8808e7` | 2026-11-05 | nothing unique | superseded: its 36 remaining edits conflict with newer main versions |
| `feat/studio-d-dual-runtime-offline-verify-20261031-r06` | `86320cb072` | 2026-11-05 | nothing unique | superseded: its 5 remaining edits conflict with newer main versions |
| `feat/studio-dual-v1-v2-package-attestation-20261030` | `40f6399ab4` | 2026-10-30 | ported in PR #5767 | all 55 new / 0 modified surviving paths are carried by the port (7 test modules held: fail on source branch too) |
| `feat/studio-durable-operator-pause-20261030` | `75fd98eeb0` | 2026-10-30 | ported in PR #5767 | all 34 new / 0 modified surviving paths are carried by the port (1 test modules held: fail on source branch too) |
| `feat/studio-durable-original-media-20261030` | `6e3f59a7fe` | 2026-10-30 | ported in PR #5767 | all 49 new / 0 modified surviving paths are carried by the port (5 test modules held: fail on source branch too) |
| `feat/studio-durable-quest-checkpoints-20261030` | `5eb752d3e6` | 2026-10-30 | ported in PR #5767 | all 37 new / 0 modified surviving paths are carried by the port (1 test modules held: fail on source branch too) |
| `feat/studio-durable-source-bound-walk-checkpoints-20261030` | `b210ba3600` | 2026-10-30 | ported in PR #5767 | all 68 new / 0 modified surviving paths are carried by the port (15 test modules held: fail on source branch too) |
| `feat/studio-ecosystem-catalog-20261030` | `3cbe5950cf` | 2026-10-31 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; 74 paths already carried by port PRs; e.g. tests/test_studio_ecosystem_catalog_fd_security.py |
| `feat/studio-ecosystem-wave2-20261030` | `ff87d4f82a` | 2026-10-30 | ported in PR #5767 | all 4 new / 0 modified surviving paths are carried by the port |
| `feat/studio-ending-obligations-20261030` | `4964021341` | 2026-10-30 | ported in PR #5767 | all 17 new / 0 modified surviving paths are carried by the port |
| `feat/studio-executable-physics-transcript-cli-20261030` | `91e6d1822c` | 2026-10-30 | ported in PR #5767 | all 66 new / 0 modified surviving paths are carried by the port (14 test modules held: fail on source branch too) |
| `feat/studio-faction-replay-20261030` | `1ba856cdd8` | 2026-10-30 | ported in PR #5767 | all 13 new / 0 modified surviving paths are carried by the port |
| `feat/studio-fail-closed-rights-20261030` | `a87252c7ad` | 2026-10-30 | ported in PR #5767 | all 21 new / 0 modified surviving paths are carried by the port |
| `feat/studio-full-catalog-continuity-audit-20261030` | `18ca303ac0` | 2026-10-30 | ported in PR #5767 | all 9 new / 0 modified surviving paths are carried by the port |
| `feat/studio-full-catalog-media-audit-20261030` | `ec56e491fe` | 2026-10-30 | ported in PR #5767 | all 53 new / 0 modified surviving paths are carried by the port (5 test modules held: fail on source branch too) |
| `feat/studio-git-admission-20261030` | `61714e30dc` | 2026-10-30 | ported in PR #5767 | all 73 new / 0 modified surviving paths are carried by the port (18 test modules held: fail on source branch too) |
| `feat/studio-guarded-durable-supervisor-20261030` | `9591e2f21c` | 2026-10-30 | ported in PR #5767 | all 35 new / 0 modified surviving paths are carried by the port (1 test modules held: fail on source branch too) |
| `feat/studio-hardware-adaptive-production-20261030` | `02121a03ae` | 2026-10-30 | ported in PR #5767 | all 23 new / 0 modified surviving paths are carried by the port |
| `feat/studio-interactive-object-index-20261030` | `395517c4ef` | 2026-10-30 | ported in PR #5767 | all 19 new / 0 modified surviving paths are carried by the port |
| `feat/studio-interactive-story-operator-cli-20261030` | `219c092300` | 2026-10-30 | ported in PR #5767 | all 56 new / 0 modified surviving paths are carried by the port (8 test modules held: fail on source branch too) |
| `feat/studio-isolated-project-portfolio-20261030` | `2917858cd7` | 2026-10-30 | ported in PR #5767 | all 47 new / 0 modified surviving paths are carried by the port (4 test modules held: fail on source branch too) |
| `feat/studio-journal-chain-audit-20261030` | `a4304b31cb` | 2026-10-30 | ported in PR #5767 | all 29 new / 0 modified surviving paths are carried by the port |
| `feat/studio-live-multiproject-cli-20261030` | `488322c032` | 2026-10-30 | ported in PR #5767 | all 49 new / 0 modified surviving paths are carried by the port (5 test modules held: fail on source branch too) |
| `feat/studio-live-source-fence-20261030` | `d6c1b8ac4e` | 2026-10-30 | ported in PR #5767 | all 33 new / 0 modified surviving paths are carried by the port (1 test modules held: fail on source branch too) |
| `feat/studio-local-evidence-submissions-20261030` | `546829b417` | 2026-10-30 | ported in PR #5767 | all 33 new / 0 modified surviving paths are carried by the port (1 test modules held: fail on source branch too) |
| `feat/studio-local-operator-cli-20261030` | `6bf2cc4ee8` | 2026-10-30 | ported in PR #5767 | all 39 new / 0 modified surviving paths are carried by the port (1 test modules held: fail on source branch too) |
| `feat/studio-measured-svg-wav-quality-20261030` | `16dc94b818` | 2026-10-30 | ported in PR #5767 | all 49 new / 0 modified surviving paths are carried by the port (5 test modules held: fail on source branch too) |
| `feat/studio-operator-lease-recovery-20261030` | `7f56c5393a` | 2026-10-30 | ported in PR #5767 | all 29 new / 0 modified surviving paths are carried by the port |
| `feat/studio-optin-parallel-operator-production-20261030` | `f1e0a7f945` | 2026-10-30 | ported in PR #5767 | all 59 new / 0 modified surviving paths are carried by the port (9 test modules held: fail on source branch too) |
| `feat/studio-optional-interactive-quest-package-20261030` | `11f02136b2` | 2026-10-30 | ported in PR #5767 | all 55 new / 0 modified surviving paths are carried by the port (7 test modules held: fail on source branch too) |
| `feat/studio-original-entry-dag-20261030` | `557e34d8ac` | 2026-10-30 | ported in PR #5767 | all 11 new / 0 modified surviving paths are carried by the port |
| `feat/studio-original-offline-media-bundle-20261030` | `436a46a5c3` | 2026-10-30 | ported in PR #5767 | all 49 new / 0 modified surviving paths are carried by the port (5 test modules held: fail on source branch too) |
| `feat/studio-original-scene-binding-20261030` | `ee3003d384` | 2026-10-30 | ported in PR #5767 | all 11 new / 0 modified surviving paths are carried by the port |
| `feat/studio-original-svg-terrain-20261030` | `eb89573556` | 2026-10-30 | ported in PR #5767 | all 42 new / 0 modified surviving paths are carried by the port (1 test modules held: fail on source branch too) |
| `feat/studio-original-wave-synth-20261030` | `e292832fbd` | 2026-10-30 | ported in PR #5767 | all 42 new / 0 modified surviving paths are carried by the port (1 test modules held: fail on source branch too) |
| `feat/studio-playable-canvas-npc-dialogue-20261030` | `78c4f525e9` | 2026-10-30 | ported in PR #5767 | all 70 new / 0 modified surviving paths are carried by the port (17 test modules held: fail on source branch too) |
| `feat/studio-playable-original-2d-scenes-20261030` | `976ef61432` | 2026-10-30 | ported in PR #5767 | all 56 new / 0 modified surviving paths are carried by the port (8 test modules held: fail on source branch too) |
| `feat/studio-player-controlled-shortest-route-hints-20261030` | `f089f76931` | 2026-10-30 | ported in PR #5767 | all 68 new / 0 modified surviving paths are carried by the port (15 test modules held: fail on source branch too) |
| `feat/studio-preserve-partial-exports-20261030` | `838d2314d2` | 2026-10-30 | ported in PR #5767 | all 51 new / 0 modified surviving paths are carried by the port (5 test modules held: fail on source branch too) |
| `feat/studio-private-durable-journal-20261030` | `22cbfa558b` | 2026-10-30 | ported in PR #5767 | all 29 new / 0 modified surviving paths are carried by the port |
| `feat/studio-producer-cas-leases-20261030` | `556ec34957` | 2026-10-30 | ported in PR #5767 | all 25 new / 0 modified surviving paths are carried by the port |
| `feat/studio-production-dependency-graph-20261030` | `b42d4efa72` | 2026-10-30 | ported in PR #5767 | all 23 new / 0 modified surviving paths are carried by the port |
| `feat/studio-production-operator-cli-20261030` | `4909fefe7b` | 2026-10-30 | ported in PR #5767 | all 29 new / 0 modified surviving paths are carried by the port |
| `feat/studio-quest-bound-scene-20261030` | `bf2de9db53` | 2026-10-30 | ported in PR #5767 | all 13 new / 0 modified surviving paths are carried by the port |
| `feat/studio-quest-cli-20261030` | `738ac81efb` | 2026-10-30 | ported in PR #5767 | all 9 new / 0 modified surviving paths are carried by the port |
| `feat/studio-quest-playthrough-runtime-20261030` | `968ed7c736` | 2026-10-30 | ported in PR #5767 | all 5 new / 0 modified surviving paths are carried by the port |
| `feat/studio-quest-route-coverage-20261030` | `1e9b7467c1` | 2026-10-30 | ported in PR #5767 | all 10 new / 0 modified surviving paths are carried by the port |
| `feat/studio-real-canvas-hazard-health-runtime-20261030` | `be56419b80` | 2026-10-30 | ported in PR #5767 | all 68 new / 0 modified surviving paths are carried by the port (15 test modules held: fail on source branch too) |
| `feat/studio-real-preview-artifact-20261030` | `7fc68cbbc3` | 2026-10-30 | ported in PR #5767 | all 37 new / 0 modified surviving paths are carried by the port (1 test modules held: fail on source branch too) |
| `feat/studio-real-production-throughput-20261030` | `c726f21915` | 2026-10-30 | ported in PR #5767 | all 51 new / 0 modified surviving paths are carried by the port (5 test modules held: fail on source branch too) |
| `feat/studio-resource-admitted-parallel-game-production-20261030` | `2ac29753f2` | 2026-10-30 | ported in PR #5767 | all 58 new / 0 modified surviving paths are carried by the port (9 test modules held: fail on source branch too) |
| `feat/studio-resource-conservation-20261030` | `c9f923959d` | 2026-10-30 | ported in PR #5767 | all 15 new / 0 modified surviving paths are carried by the port |
| `feat/studio-resource-weighted-batches-20261030` | `8e2b15dd10` | 2026-10-30 | ported in PR #5767 | all 27 new / 0 modified surviving paths are carried by the port |
| `feat/studio-safe-restart-inspection-20261030` | `54617b949f` | 2026-10-30 | ported in PR #5767 | all 33 new / 0 modified surviving paths are carried by the port (1 test modules held: fail on source branch too) |
| `feat/studio-seven-file-walkable-world-bundle-20261030` | `d1bcadffdd` | 2026-10-30 | ported in PR #5767 | all 56 new / 0 modified surviving paths are carried by the port (8 test modules held: fail on source branch too) |
| `feat/studio-source-audio-cues-20261030` | `410a14f6b8` | 2026-10-30 | ported in PR #5767 | all 19 new / 0 modified surviving paths are carried by the port |
| `feat/studio-source-authored-2d-encounter-hazards-20261030` | `efa3b46b26` | 2026-10-30 | ported in PR #5767 | all 68 new / 0 modified surviving paths are carried by the port (15 test modules held: fail on source branch too) |
| `feat/studio-source-aware-shortest-navigation-20261030` | `f979455f82` | 2026-10-30 | ported in PR #5767 | all 65 new / 0 modified surviving paths are carried by the port (14 test modules held: fail on source branch too) |
| `feat/studio-source-manifest-chains-20261030` | `2c545938e5` | 2026-10-30 | ported in PR #5767 | all 25 new / 0 modified surviving paths are carried by the port |
| `feat/studio-source-npc-dialogue-proof-20261030` | `35aab48b8d` | 2026-10-30 | ported in PR #5767 | all 71 new / 0 modified surviving paths are carried by the port (18 test modules held: fail on source branch too) |
| `feat/studio-source-original-npc-patrols-20261030` | `dc0c460a87` | 2026-10-30 | ported in PR #5767 | all 69 new / 0 modified surviving paths are carried by the port (16 test modules held: fail on source branch too) |
| `feat/studio-source-pinned-full-portfolio-evidence-census-20261030` | `a51ddf2a1d` | 2026-10-30 | ported in PR #5767 | all 61 new / 0 modified surviving paths are carried by the port (11 test modules held: fail on source branch too) |
| `feat/studio-streaming-artifact-spool-20261030` | `203898297b` | 2026-10-30 | ported in PR #5767 | all 31 new / 0 modified surviving paths are carried by the port (1 test modules held: fail on source branch too) |
| `feat/studio-streaming-spool-audit-20261030` | `b9e73c57ae` | 2026-10-30 | ported in PR #5767 | all 39 new / 0 modified surviving paths are carried by the port (1 test modules held: fail on source branch too) |
| `feat/studio-synthetic-full-quest-playthrough-20261030` | `fb10c9f94d` | 2026-10-30 | ported in PR #5767 | all 66 new / 0 modified surviving paths are carried by the port (14 test modules held: fail on source branch too) |
| `feat/studio-three-mode-concurrent-game-builds-20261030` | `a0785d56f0` | 2026-10-30 | ported in PR #5767 | all 58 new / 0 modified surviving paths are carried by the port (9 test modules held: fail on source branch too) |
| `feat/studio-true-host-swap-gpu-resource-telemetry-20261030` | `53981f19ac` | 2026-10-30 | ported in PR #5767 | all 58 new / 0 modified surviving paths are carried by the port (9 test modules held: fail on source branch too) |
| `feat/studio-unified-production-frame-20261030` | `bdce40a9fc` | 2026-10-30 | ported in PR #5767 | all 27 new / 0 modified surviving paths are carried by the port |
| `feat/studio-v3-adaptive-multiproject-production-20261030` | `94a08be5bf` | 2026-10-30 | ported in PR #5767 | all 56 new / 0 modified surviving paths are carried by the port (8 test modules held: fail on source branch too) |
| `feat/studio-v3-walkable-content-verifier-20261030` | `57ac54a703` | 2026-10-30 | ported in PR #5767 | all 56 new / 0 modified surviving paths are carried by the port (8 test modules held: fail on source branch too) |
| `feat/studio-verified-browser-physics-history-20261030` | `8b9aaa83ae` | 2026-10-30 | ported in PR #5767 | all 65 new / 0 modified surviving paths are carried by the port (14 test modules held: fail on source branch too) |
| `feat/studio-verified-operator-resume-cli-20261030` | `9094364646` | 2026-10-30 | ported in PR #5767 | all 59 new / 0 modified surviving paths are carried by the port (9 test modules held: fail on source branch too) |
| `feat/studio-verified-resumable-production-20261030` | `9c876b4356` | 2026-10-30 | ported in PR #5767 | all 53 new / 0 modified surviving paths are carried by the port (5 test modules held: fail on source branch too) |
| `feat/studio-verified-stream-export-20261030` | `94b05658cb` | 2026-10-30 | ported in PR #5767 | all 43 new / 0 modified surviving paths are carried by the port (1 test modules held: fail on source branch too) |
| `feat/studio-walkable-game-operator-cli-20261030` | `8112ff1691` | 2026-10-30 | ported in PR #5767 | all 56 new / 0 modified surviving paths are carried by the port (8 test modules held: fail on source branch too) |
| `feat/studio-wave2-slice01-20261030` | `4b87d3f2b2` | 2026-10-30 | ported in PR #5767 | all 43 new / 0 modified surviving paths are carried by the port (1 test modules held: fail on source branch too) |
| `feat/studio-wave2-slice02-20261030` | `40e26a2f6d` | 2026-10-30 | ported in PR #5767 | all 3 new / 0 modified surviving paths are carried by the port |
| `feat/studio-wave2-slice03-20261030` | `eaecf7040f` | 2026-10-30 | ported in PR #5767 | all 3 new / 0 modified surviving paths are carried by the port |
| `feat/studio-wave2-slice04-20261030` | `e3a1333a3f` | 2026-10-30 | ported in PR #5767 | all 3 new / 0 modified surviving paths are carried by the port |
| `feat/studio-wave2-slice05-20261030` | `0a9f6effba` | 2026-10-30 | ported in PR #5767 | all 3 new / 0 modified surviving paths are carried by the port |
| `feat/studio-wave2-slice06-20261030` | `9787275368` | 2026-10-30 | ported in PR #5767 | all 3 new / 0 modified surviving paths are carried by the port |
| `feat/studio-wave2-slice07-20261030` | `1baec992ee` | 2026-10-30 | ported in PR #5767 | all 3 new / 0 modified surviving paths are carried by the port |
| `feat/studio-wave2-slice08-20261030` | `78d76c432a` | 2026-10-30 | ported in PR #5767 | all 3 new / 0 modified surviving paths are carried by the port |
| `feat/studio-wave2-slice09-20261030` | `271dc729b5` | 2026-10-30 | ported in PR #5767 | all 3 new / 0 modified surviving paths are carried by the port |
| `feat/studio-wave2-slice10-20261030` | `abe8fdf67c` | 2026-10-30 | ported in PR #5767 | all 3 new / 0 modified surviving paths are carried by the port |
| `feat/studio-wave2-slice11-20261030` | `3c5d0a260d` | 2026-10-30 | ported in PR #5767 | all 3 new / 0 modified surviving paths are carried by the port |
| `feat/studio-wave2-slice12-20261030` | `a95220edd1` | 2026-10-30 | ported in PR #5767 | all 3 new / 0 modified surviving paths are carried by the port |
| `feat/studio-wave2-slice13-20261030` | `dc95c74d14` | 2026-10-30 | ported in PR #5767 | all 3 new / 0 modified surviving paths are carried by the port |
| `feat/studio-wave2-slice14-20261030` | `5f9c6f7354` | 2026-10-30 | ported in PR #5767 | all 3 new / 0 modified surviving paths are carried by the port |
| `feat/studio-wave2-slice15-20261030` | `6c6c883e89` | 2026-10-30 | ported in PR #5767 | all 3 new / 0 modified surviving paths are carried by the port |
| `feat/studio-wave2-slice16-20261030` | `681ea213fd` | 2026-10-30 | ported in PR #5767 | all 3 new / 0 modified surviving paths are carried by the port |
| `feat/studio-wave2-slice17-20261030` | `5fdbb3ba09` | 2026-10-30 | ported in PR #5767 | all 3 new / 0 modified surviving paths are carried by the port |
| `feat/studio-wave2-slice18-20261030` | `02ab47a50d` | 2026-10-30 | ported in PR #5767 | all 3 new / 0 modified surviving paths are carried by the port |
| `feat/studio-wave2-slice19-20261030` | `0a3b15139d` | 2026-10-30 | ported in PR #5767 | all 3 new / 0 modified surviving paths are carried by the port |
| `feat/studio-wave2-slice20-20261030` | `2020bf0edd` | 2026-10-30 | ported in PR #5767 | all 3 new / 0 modified surviving paths are carried by the port |
| `feat/studio-wave2-slice21-20261030` | `1b7b47c914` | 2026-10-30 | ported in PR #5767 | all 3 new / 0 modified surviving paths are carried by the port |
| `feat/studio-wave2-slice22-20261030` | `1fce6f64da` | 2026-10-30 | ported in PR #5767 | all 3 new / 0 modified surviving paths are carried by the port |
| `feat/studio-wave2-slice23-20261030` | `49b332466b` | 2026-10-30 | ported in PR #5767 | all 3 new / 0 modified surviving paths are carried by the port |
| `feat/studio-wave2-slice24-20261030` | `4b93c24d86` | 2026-10-30 | ported in PR #5767 | all 3 new / 0 modified surviving paths are carried by the port |
| `feat/studio-wave2-slice25-20261030` | `4898a3df77` | 2026-10-30 | ported in PR #5767 | all 3 new / 0 modified surviving paths are carried by the port |
| `feat/studio-wave2-slice26-20261030` | `8676db20c7` | 2026-10-30 | ported in PR #5767 | all 3 new / 0 modified surviving paths are carried by the port |
| `feat/studio-wave2-slice27-20261030` | `deaea5f533` | 2026-10-30 | ported in PR #5767 | all 3 new / 0 modified surviving paths are carried by the port |
| `feat/studio-wave2-slice28-20261030` | `c2c60f1af7` | 2026-10-30 | ported in PR #5767 | all 3 new / 0 modified surviving paths are carried by the port |
| `feat/studio-wave2-slice29-20261030` | `1e2f54d264` | 2026-10-30 | ported in PR #5767 | all 3 new / 0 modified surviving paths are carried by the port |
| `feat/studio-wave2-slice30-20261030` | `505263c5cc` | 2026-10-30 | ported in PR #5767 | all 3 new / 0 modified surviving paths are carried by the port |
| `feat/studio-wave2-slice31-20261030` | `74bf0cad67` | 2026-10-30 | ported in PR #5767 | all 3 new / 0 modified surviving paths are carried by the port |
| `feat/studio-wave2-slice32-20261030` | `3c57015725` | 2026-10-30 | ported in PR #5767 | all 5 new / 0 modified surviving paths are carried by the port |
| `feat/telemetry-121-extend` | `8bf06e2c88` | 2026-11-16 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `feat/ui-art-foundation-tokens` | `2916af15d6` | 2026-10-17 | ported in PR #5771 | all 0 new / 1 modified surviving paths are carried by the port |
| `feat/unified-operator-ui-20261016` | `f1c3047319` | 2026-10-16 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. tests/test_product_workspace_and_native_stops.py |
| `feat/vol249-250-evidence-causal-reasoning-20261107` | `78603b5c76` | 2026-11-09 | fully on main | every changed blob already on main |
| `feat/walt-realtime-transport-20261017` | `40d412797e` | 2026-10-17 | nothing unique | superseded: its 18 remaining edits conflict with newer main versions |
| `feat/world-events-50-regional-directors-20261031` | `e559df4686` | 2026-11-05 | fully on main | every changed blob already on main |
| `feature/dragon-lens-postmerge-integration-20261017` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feature/galaxy-gameforge-full-design-handoff-20261113-r01` | `abec5307de` | 2026-11-14 | nothing unique | superseded: its 20 remaining edits conflict with newer main versions |
| `feature/game-frontier-p0-p3-20261019` | `248492d8a3` | 2026-11-13 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `feature/gameforge-multigenre-playable-slices-20261113-r01` | `b26ea7e369` | 2026-11-16 | unique content pending port | 0 new files, 26 modified files survive a 3-way merge; open PR #5315 (conflicting) -> main |
| `feature/jeeves-full-lens-training-review-20261017` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feature/jeeves-native-book-studio-20261021` | `8dd4ac841d` | 2026-11-13 | fully on main | every changed blob already on main |
| `feature/quest-runtime-godot-integration-20261113-r01` | `8a3808f7ca` | 2026-11-14 | nothing unique | superseded: its 10 remaining edits conflict with newer main versions |
| `feature/recover-archived-input-script-runtime-20261113-r01` | `257343ac78` | 2026-11-14 | nothing unique | superseded: its 5 remaining edits conflict with newer main versions |
| `feature/recover-gameforge-design-instruments-20261113-r01` | `56123d1edd` | 2026-11-14 | nothing unique | superseded: its 17 remaining edits conflict with newer main versions |
| `feature/restore-archived-gameforge-conductor-20261113-r01` | `3a44e79827` | 2026-11-14 | nothing unique | superseded: its 7 remaining edits conflict with newer main versions |
| `feature/restore-archived-quest-genre-synthesis-20261113-r01` | `90099e8f73` | 2026-11-14 | nothing unique | superseded: its 5 remaining edits conflict with newer main versions |
| `feature/rom-learning-batch-20261017` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feature/sdk-learning-custody-20261017` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `feature/unify-galaxy-quest-gameforge-20261113-r01` | `96ed5c22b0` | 2026-11-14 | nothing unique | superseded: its 20 remaining edits conflict with newer main versions |
| `fix/4287-migration-overlay-tests-20261028` | `e497efc66b` | 2026-10-28 | unique content pending port | 0 new files, 24 modified files survive a 3-way merge |
| `fix/agent-swarm-graph-durability-20261105` | `a902482466` | 2026-11-09 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/ai-cognition-integration-and-scope-20261103` | `8a02a09782` | 2026-11-05 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `fix/ai-file-tree-overlay-owners` | `5e3bbf4d9f` | 2026-10-17 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `fix/ai-file-tree-parity-39985171215` | `25b5aa956b` | 2026-10-24 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/ai-flight-portable-owned-fixture-20261107` | `1792d909cd` | 2026-11-07 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/ai-mirror-parity-first-install-20261105` | `58f2bd9ce0` | 2026-11-09 | unique content pending port | 2 new files, 4 modified files survive a 3-way merge; e.g. skeleton/testing/test_jeeves_desktop_request_deadline_fence.py, tests/test_ai_tree_source_pins.py |
| `fix/ai-nvml-unavailable-receipt-20261031-conveyor` | `560236f5b6` | 2026-11-05 | fully on main | every changed blob already on main |
| `fix/ai-parity-integrated-qualification-20261105` | `2f1463d43b` | 2026-11-09 | unique content pending port | 3 new files, 0 modified files survive a 3-way merge; e.g. machine/jeeves_source_ci_trigger_registry.json, scripts/check_jeeves_source_ci_scope.py, tests/test_jeeves_source_ci_scope.py |
| `fix/ai-tree-caravans-mirror-20261030` | `0ad0531cca` | 2026-11-05 | unique content pending port | 21 new files, 7 modified files survive a 3-way merge; 1 paths already carried by port PRs; e.g. docs/ai/KV_INDEPENDENT_ROLLBACK_ANCHOR.md, docs/ai/KV_LIVE_TIER_CONTROLLER.md, docs/ai/KV_MIGRATION_JOURNAL.md |
| `fix/ai-tree-exact-source-parity-20261108` | `c29f206262` | 2026-11-09 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. tests/test_ai_tree_source_mirror_20261108.py |
| `fix/ai-tree-forge-audio-mass-build-parity-20261105` | `ff52d899b6` | 2026-11-09 | unique content pending port | 3 new files, 0 modified files survive a 3-way merge; e.g. machine/jeeves_source_ci_trigger_registry.json, scripts/check_jeeves_source_ci_scope.py, tests/test_jeeves_source_ci_scope.py |
| `fix/ai-tree-jeeves-mirror-symlink-guard-20261031` | `cc8da0e0b6` | 2026-11-05 | unique content pending port | 21 new files, 7 modified files survive a 3-way merge; 1 paths already carried by port PRs; e.g. docs/ai/KV_INDEPENDENT_ROLLBACK_ANCHOR.md, docs/ai/KV_LIVE_TIER_CONTROLLER.md, docs/ai/KV_MIGRATION_JOURNAL.md |
| `fix/ai-tree-native-owner-overlap-20261016` | `e31c5f1644` | 2026-10-16 | nothing unique | superseded: its 20 remaining edits conflict with newer main versions |
| `fix/ai-tree-owner-parity-20261016` | `49ad8705e4` | 2026-10-16 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `fix/ai-tree-parity-audio-mass-build-20261105` | `d1169a372b` | 2026-11-05 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. tests/test_ai_tree_20261105_recovery.py |
| `fix/ai-tree-parity-sync-20261023` | `6bec50adb7` | 2026-10-23 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/ai-tree-resync-20261109` | `bd5112ccdb` | 2026-11-10 | fully on main | every changed blob already on main |
| `fix/ai-tree-retained-root-owners-20261023` | `9be1bdba16` | 2026-10-23 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/ai-tree-runtime-mirror-parity-20261023` | `b01589023a` | 2026-10-23 | nothing unique | superseded: its 8 remaining edits conflict with newer main versions |
| `fix/ai-tree-syntax-membership-failclosed-20261105` | `1bc884922f` | 2026-11-09 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/aift-application-source-sha-20261113` | `a6f68bcc36` | 2026-11-14 | nothing unique | superseded: its 5 remaining edits conflict with newer main versions |
| `fix/antipattern-exception-admission-20261026` | `3c5ff5d897` | 2026-10-26 | fully on main | every changed blob already on main |
| `fix/app-assembly-canonical-paths-20261018` | `401f386567` | 2026-10-18 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/app-e2e-node-forge-143-20261112` | `7ab85a0886` | 2026-11-14 | ported in PR #5771 | all 0 new / 1 modified surviving paths are carried by the port |
| `fix/app-foundation-playwright-ubuntu24-20261026` | `3819ec3893` | 2026-10-26 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/asyncio-loop-local-admission-20261018` | `a6c613990e` | 2026-10-18 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/authority-bundle-aggregate-20261026` | `2fdbc3e5d8` | 2026-10-26 | fully on main | every changed blob already on main |
| `fix/automation-model-direct-egress-ci-20261109` | `68d8ad2069` | 2026-11-09 | fully on main | every changed blob already on main |
| `fix/automation-traffic-dispatch-import-40062674483` | `ac06a5ef7d` | 2026-10-24 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/automerge-bounded-eight-squash-batch-20261109` | `d0b163108e` | 2026-11-10 | fully on main | every changed blob already on main |
| `fix/automerge-explicit-text-holds-isolated-20261111` | `b77e9c6b04` | 2026-11-11 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/automerge-pr-text-hold-custody-20261110-r01` | `cbe5221247` | 2026-11-10 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. tests/test_ai_tree_replay_provider_coverage_20261110.py |
| `fix/backend-chat-contract-regressions-39985171215` | `f771c9765f` | 2026-10-24 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/backend-chat-prepared-fixtures-18-20261024` | `645c9ef6ea` | 2026-10-24 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/backend-engine-replay-and-resource-assertions-20261020` | `3f47469223` | 2026-10-20 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/backend-live-boundary-hermetic-misclassification-20261110-r01` | `96704d768b` | 2026-11-11 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/backend-python-pin-and-runtime-pip-20261105` | `373fd21b58` | 2026-11-09 | nothing unique | superseded: its 8 remaining edits conflict with newer main versions |
| `fix/backend-source-mainline-convergence-20261110-r01` | `2b1012ef5d` | 2026-11-11 | nothing unique | superseded: its 13 remaining edits conflict with newer main versions |
| `fix/branch-retirement-custody-20261016` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `fix/branch-retirement-readonly-custody-20261016` | `2e8f8ab539` | 2026-10-16 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/build-order-completion-admission-20261026` | `04871ea38e` | 2026-10-26 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/build-order-iterative-graph-20261026` | `dc451b92e4` | 2026-10-26 | fully on main | every changed blob already on main |
| `fix/canonical-ai-mirror-parity-20261107` | `caf88c369f` | 2026-11-10 | nothing unique | superseded: its 17 remaining edits conflict with newer main versions |
| `fix/canonical-formal-binding-no-import-20261026` | `245541c079` | 2026-10-26 | fully on main | every changed blob already on main |
| `fix/chat-authority-prepared-fixtures-20261024` | `80c3742841` | 2026-10-24 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/chat-conversation-authority-fixtures-20261024` | `8b3ecff5bc` | 2026-10-24 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `fix/chat-engine-offline-admission-regression-20261024` | `78a78f0057` | 2026-10-24 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/chat-engine-unavailable-preflight-test-20261024` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `fix/chat-finalization-prepared-fixtures-20261024` | `5faefb2396` | 2026-10-24 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/chat-memory-atomic-fixture-clean-20261024` | `7731d71a13` | 2026-10-24 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/chat-turn-prepared-harness-20261024` | `ee528caf6d` | 2026-10-24 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/chronological-audit-godot-custody-20261115` | `c753931d6e` | 2026-11-16 | fully on main | every changed blob already on main |
| `fix/chronological-audit-july-workflow-prood-20261115` | `508ce7dd04` | 2026-11-16 | fully on main | every changed blob already on main |
| `fix/chronological-coverage-evidence-20261115` | `3df1f17c8c` | 2026-11-16 | unique content pending port | 3 new files, 2 modified files survive a 3-way merge; open PR #5434 (conflicting) -> fix/chronological-lafs-evidence-custody-20261115; e.g. backend/gameforge/coverage_inventory.py, backend/tests/test_chronological_coverage_inventory.py, docs/chronological-coverage-evidence.md |
| `fix/chronological-lafs-evidence-custody-20261115` | `4a2ed4bed3` | 2026-11-16 | fully on main | every changed blob already on main |
| `fix/chronological-omega-lifecycle-20261115` | `8df411dd1b` | 2026-11-16 | fully on main | every changed blob already on main |
| `fix/chronological-retained-event-custody-20261115` | `683be3501b` | 2026-11-16 | fully on main | every changed blob already on main |
| `fix/chronological-route-registry-custody-20261115` | `d4a8ac9542` | 2026-11-16 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/chronological-vault-delivery-custody-20261115` | `0ca40d37b1` | 2026-11-20 | unique content pending port | 5 new files, 3 modified files survive a 3-way merge; open PR #5432 (mergeable) -> fix/chronological-audit-july-workflow-prood-20261115; e.g. backend/gameforge/workflow/delivery_scope.py, backend/tests/test_chronological_delivery_scope.py, docs/gameforge-delivery-custody-v2.md |
| `fix/ci-active-archived-contract-alignment-20261020` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `fix/ci-ai-tree-failfast-20261025` | `00835445e4` | 2026-10-25 | fully on main | every changed blob already on main |
| `fix/ci-archived-workflow-contracts-20261020` | `e4fa7ef55f` | 2026-10-20 | nothing unique | superseded: its 9 remaining edits conflict with newer main versions |
| `fix/ci-automatic-admission-cap-20261028` | `b0c43510f2` | 2026-10-28 | unique content pending port | 0 new files, 2 modified files survive a 3-way merge |
| `fix/ci-backend-fastapi-parity-20261026` | `632169bc1a` | 2026-10-26 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/ci-canonical-contract-fixtures-20261031-conveyor` | `5f132fb714` | 2026-11-05 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/ci-dynamic-import-transitive-alias-closure-20261111-r01` | `0dc02d9eeb` | 2026-11-11 | fully on main | every changed blob already on main |
| `fix/ci-ecosystem-flat-backend-import-20261111-r01` | `ad4d83cc11` | 2026-11-11 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/ci-expo-sdk54-pairing-guard-20261026` | `ff527ed699` | 2026-10-26 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `fix/ci-galaxy-vault-pending-contract-20261111-r01` | `21e38bc16c` | 2026-11-11 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/ci-harbor-cli-studio-archive-custody-20261111-r01` | `34aeefa882` | 2026-11-11 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `fix/ci-harbor-patrol-dispatch-20261111-r01` | `c1de2abda7` | 2026-11-11 | nothing unique | superseded: its 13 remaining edits conflict with newer main versions |
| `fix/ci-idempotency-wrapper-audit-20261031-conveyor` | `eca13e25a2` | 2026-11-05 | unique content pending port | 0 new files, 2 modified files survive a 3-way merge |
| `fix/ci-integration-httpx-floor-20261026` | `b3a9fac824` | 2026-10-26 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/ci-inventory-ownership-20261016` | `f4dc79e9da` | 2026-10-16 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge; 1 paths already carried by port PRs |
| `fix/ci-jeeves-caravan-mirror-index-20261031-conveyor` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `fix/ci-lazy-registry-public-route-extract-20261111-r01` | `ff890888f3` | 2026-11-11 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/ci-mainline-source-convergence-20261110-r02` | `5a03e1a626` | 2026-11-11 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `fix/ci-mass-exact-head-regression-coverage-20261110-r02` | `d6580a8c1a` | 2026-11-11 | unique content pending port | 12 new files, 54 modified files survive a 3-way merge; 1 paths already carried by port PRs; e.g. skeleton/testing/test_game_project_cli_custody.py, skeleton/testing/test_game_project_cli_input_budget.py, skeleton/testing/test_godot_export_cli_custody.py |
| `fix/ci-mass-source-convergence-20261110-r01` | `d563210b0c` | 2026-11-11 | unique content pending port | 12 new files, 53 modified files survive a 3-way merge; 1 paths already carried by port PRs; e.g. skeleton/testing/test_game_project_cli_custody.py, skeleton/testing/test_game_project_cli_input_budget.py, skeleton/testing/test_godot_export_cli_custody.py |
| `fix/ci-native-endurance-receipt-20261111-r01` | `0b3dea5a4b` | 2026-11-11 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/ci-native-proof-custody-mainline-extract-20261111-r01` | `738a5a73f7` | 2026-11-11 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `fix/ci-native-proof-preflight-20261111-r01` | `c30a55691b` | 2026-11-11 | nothing unique | superseded: its 23 remaining edits conflict with newer main versions |
| `fix/ci-native-proof-verifier-strict-types-20261111-r01` | `c4b93ec971` | 2026-11-11 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/ci-operational-schedule-budget-20261108` | `0de2713216` | 2026-11-09 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/ci-pillow13-unit-parity-20261026` | `0df31acc8a` | 2026-10-26 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/ci-playwright-apt-dns-retry-20261111-r01` | `39a19dcc75` | 2026-11-11 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/ci-product-surface-merge-hold-custody-20261111-r01` | `ffd3251831` | 2026-11-11 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/ci-profiler-load-and-alloc-bounds-20261111-r01` | `808826bdd1` | 2026-11-11 | nothing unique | superseded: its 20 remaining edits conflict with newer main versions |
| `fix/ci-qualification-untrusted-map-keys-20261111-r01` | `6085d2cff7` | 2026-11-11 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/ci-queue-clearance-20261105` | `ddb3f6c656` | 2026-11-05 | unique content pending port | 2 new files, 0 modified files survive a 3-way merge; e.g. docs/ci/QUEUE_CLEARANCE.md, scripts/ci_queue_status.py |
| `fix/ci-relative-import-boundaries-signed-audit-20261106` | `e44e4ed441` | 2026-11-09 | unique content pending port | 2 new files, 4 modified files survive a 3-way merge; e.g. skeleton/testing/test_jeeves_desktop_request_deadline_fence.py, tests/test_ai_tree_source_pins.py |
| `fix/ci-release-token-stdin-20261018` | `71dbc5eeed` | 2026-10-18 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `fix/ci-ruff-0172-contract-pr-cancel-20261026` | `f80e5b510b` | 2026-10-28 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `fix/ci-ruff-parity-pr-scoped-cancellation-20261026` | `6ba349c470` | 2026-10-26 | unique content pending port | 0 new files, 3 modified files survive a 3-way merge |
| `fix/ci-sast-no-exec-test-regressions-20261111-r01` | `b8b6d19d49` | 2026-11-11 | fully on main | every changed blob already on main |
| `fix/ci-scope-nul-complete-diff-20261031` | `ec95841502` | 2026-10-31 | ported in PR #5767 | all 0 new / 1 modified surviving paths are carried by the port |
| `fix/ci-sdk54-native-matrix-gate-20261026` | `438561fb52` | 2026-10-26 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/ci-secure-session-identity-comment-regression-20261111-r01` | `90a38780f2` | 2026-11-11 | fully on main | every changed blob already on main |
| `fix/ci-shard-complete-domain-suite-20261031` | `17cab104f0` | 2026-11-05 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/ci-shard-complete-domain-suite-clean-20261105` | `e559e56963` | 2026-11-05 | unique content pending port | 0 new files, 2 modified files survive a 3-way merge |
| `fix/ci-storage-lazy-flagged-allowlist-20261111-r01` | `391e57abf5` | 2026-11-11 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/ci-tier-22-to-20-20261029` | `452ca21687` | 2026-10-29 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `fix/ci-tier-self-only-admissions-20261028` | `3b995c9764` | 2026-10-28 | unique content pending port | 0 new files, 6 modified files survive a 3-way merge |
| `fix/codeql-security-151` | `18ac4726fe` | 2026-10-28 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `fix/codex-content-scrutiny-reconciliation-20261024` | `75bccdb1b0` | 2026-10-25 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/compiler-truthful-verification-20261105` | `0bdadd08b4` | 2026-11-09 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/compressed-vault-descriptor-bounds-20261105` | `a05e36f47e` | 2026-11-09 | fully on main | every changed blob already on main |
| `fix/consolidated-test-battery-and-canonical-identity-20261106` | `55f175bf9c` | 2026-11-11 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `fix/consumer-readiness-notes-20261105` | `96b2e5cd86` | 2026-11-05 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. docs/ai/CONSUMER_READINESS_UPDATE_2026-11-05.md |
| `fix/contract-codegen-python-allowlist-isolated-20261030` | `0f9def044e` | 2026-10-30 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/contract-codegen-python-target-20261029` | `32c1d11129` | 2026-10-30 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge; 1 paths already carried by port PRs |
| `fix/conveyor-4516-domain-contracts-20261101-r04` | `e081f248ea` | 2026-11-01 | ported in PR #5767 | all 0 new / 1 modified surviving paths are carried by the port |
| `fix/conveyor-4516-mirror-parity-20261101-r02` | `80e14aed5b` | 2026-11-01 | ported in PR #5767 | all 0 new / 1 modified surviving paths are carried by the port |
| `fix/conveyor-4516-typed-evidence-rollback-wip-20261101-r11` | `e4025b451e` | 2026-11-01 | ported in PR #5767 | all 0 new / 1 modified surviving paths are carried by the port |
| `fix/conveyor-4594-seal-header-bounds-wip-20261101-r11` | `5942df6e77` | 2026-11-02 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/conveyor-4594-v2-nonce-custody-20261101-r02` | `ba4b9ce4da` | 2026-11-01 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/conveyor-4595-aift-mirrors-20261101-r02` | `95187d6f8a` | 2026-11-01 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/conveyor-4595-bounded-semantic-physics-wip-20261101-r11` | `cc45e3c8f2` | 2026-11-02 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/conveyor-4596-idempotency-cursor-boundary-wip-20261101-r11` | `be06d5f4b0` | 2026-11-02 | nothing unique | superseded: its 7 remaining edits conflict with newer main versions |
| `fix/conveyor-4597-nav-policy-bounds-wip-20261101-r11` | `8e5b1b1d2e` | 2026-11-02 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `fix/conveyor-4601-nonce-evidence-bounds-wip-20261101-r11` | `4fa081469e` | 2026-11-02 | unique content pending port | 2 new files, 0 modified files survive a 3-way merge; e.g. skeleton/api/nonce_store.py, tests/test_request_seal_v3_binding.py |
| `fix/conveyor-4602-secret-migration-checkpoint-wip-20261101-r11` | `128cadb078` | 2026-11-02 | unique content pending port | 11 new files, 0 modified files survive a 3-way merge; e.g. backend/core/core_v1/delivery_ops.py, backend/core/core_v1/envelope.py, backend/core/core_v1/keys.py |
| `fix/conveyor-4603-chroma-descriptor-bounds-wip-20261101-r11` | `d12d1309ba` | 2026-11-09 | fully on main | every changed blob already on main |
| `fix/conveyor-4604-rollback-health-evidence-wip-20261102-r12` | `3a6c13d23c` | 2026-11-02 | nothing unique | superseded: its 12 remaining edits conflict with newer main versions |
| `fix/conveyor-4604-rollback-lease-fence-wip-20261101-r11` | `9758854b8f` | 2026-11-01 | nothing unique | superseded: its 18 remaining edits conflict with newer main versions |
| `fix/conveyor-4604-zip-special-files-20261102-r11` | `06a4021d74` | 2026-11-02 | nothing unique | superseded: its 17 remaining edits conflict with newer main versions |
| `fix/conveyor-4605-aift-godot-classification-20261101-r02` | `7e5a02ca84` | 2026-11-01 | nothing unique | superseded: its 8 remaining edits conflict with newer main versions |
| `fix/conveyor-4605-godot-res-path-fence-wip-20261101-r11` | `71a333f83c` | 2026-11-02 | nothing unique | superseded: its 9 remaining edits conflict with newer main versions |
| `fix/conveyor-4606-canonical-bundle-paths-20261101-r04` | `ad05c4c62d` | 2026-11-01 | nothing unique | superseded: its 8 remaining edits conflict with newer main versions |
| `fix/conveyor-4606-codec-failure-boundary-wip-20261102-r12` | `9c0fbe6ff2` | 2026-11-09 | fully on main | every changed blob already on main |
| `fix/conveyor-4606-descriptor-bundle-io-wip-20261101-r11` | `4100a99ff6` | 2026-11-01 | nothing unique | superseded: its 8 remaining edits conflict with newer main versions |
| `fix/conveyor-4606-receipt-preflight-20261102-r11` | `96d0495f6e` | 2026-11-02 | nothing unique | superseded: its 8 remaining edits conflict with newer main versions |
| `fix/conveyor-4607-aift-perf-classification-20261101-r02` | `1858d59e55` | 2026-11-01 | nothing unique | superseded: its 13 remaining edits conflict with newer main versions |
| `fix/conveyor-4607-bounded-percentile-wip-20261101-r11` | `e04b6a13cb` | 2026-11-02 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. tests/perf_profiler/test_stats_boundaries.py |
| `fix/conveyor-4607-trusted-alloc-targets-20261101-r04` | `4a3daa7338` | 2026-11-01 | nothing unique | superseded: its 12 remaining edits conflict with newer main versions |
| `fix/conveyor-4608-bounded-localization-20261101-r04` | `e2588bdd0e` | 2026-11-01 | fully on main | every changed blob already on main |
| `fix/conveyor-4608-bounded-message-format-wip-20261101-r11` | `0fe7447402` | 2026-11-02 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `fix/conveyor-4609-jpeg-framing-20261102-r11` | `6cd1632336` | 2026-11-02 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `fix/conveyor-4609-manifest-atomic-20261101-r03` | `9df1157e75` | 2026-11-01 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `fix/conveyor-4609-obj-finite-metadata-20261102-r11` | `5bdeb3e759` | 2026-11-05 | fully on main | every changed blob already on main |
| `fix/conveyor-4609-png-chunk-validation-20261101-r04` | `81c406f062` | 2026-11-01 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `fix/conveyor-4609-untrusted-path-controls-wip-20261101-r11` | `3e3c433259` | 2026-11-01 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `fix/conveyor-4610-bounded-mutation-fuzz-wip-20261101-r11` | `29e1002aba` | 2026-11-02 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/conveyor-4610-mutation-noexec-20261101-r02` | `62dbb21c13` | 2026-11-01 | nothing unique | superseded: its 6 remaining edits conflict with newer main versions |
| `fix/conveyor-4614-forge-ai-builder-mirror-20261101-r02` | `b2acaf7879` | 2026-11-01 | nothing unique | superseded: its 7 remaining edits conflict with newer main versions |
| `fix/conveyor-4614-provider-grant-bounds-wip-20261101-r11` | `203fb7b9f0` | 2026-11-05 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `fix/conveyor-4620-quest-identity-canonical-wip-20261101-r11` | `cca5615583` | 2026-11-02 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/conveyor-4620-quest-progress-fences-20261101-r04` | `4eb4f9eadc` | 2026-11-01 | fully on main | every changed blob already on main |
| `fix/conveyor-4621-bounded-analytics-20261101-r04` | `1d9b6a4d5e` | 2026-11-01 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `fix/conveyor-4621-pseudonym-session-boundary-wip-20261101-r11` | `02c52981cc` | 2026-11-02 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `fix/conveyor-4622-secret-diagnostic-bounds-wip-20261101-r11` | `c9f7fdd9e3` | 2026-11-02 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/conveyor-4623-bounded-gameplay-migration-wip-20261101-r11` | `127eabd24f` | 2026-11-02 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/conveyor-4624-plugin-contract-bounds-wip-20261101-r11` | `948393799a` | 2026-11-02 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `fix/conveyor-4625-domain-nonce-adapter-wip-20261101-r11` | `739d068c0b` | 2026-11-01 | fully on main | every changed blob already on main |
| `fix/conveyor-4625-proxy-cert-ambiguity-20261102-r11` | `05d561305e` | 2026-11-02 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `fix/conveyor-4625-s2s-scope-canonical-wip-20261102-r12` | `3c74953b11` | 2026-11-02 | unique content pending port | 0 new files, 2 modified files survive a 3-way merge |
| `fix/conveyor-4875-loopback-assembly-20261108` | `86134254ba` | 2026-11-09 | unique content pending port | 9 new files, 52 modified files survive a 3-way merge; 1 paths already carried by port PRs; e.g. skeleton/testing/test_game_project_cli_custody.py, skeleton/testing/test_game_project_cli_input_budget.py, skeleton/testing/test_godot_export_cli_custody.py |
| `fix/conveyor-archive-epoch-validation-20261102` | `332eaf2d98` | 2026-11-05 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `fix/conveyor-artifact-alias-verification-20261102` | `914fc62c78` | 2026-11-03 | nothing unique | superseded: its 14 remaining edits conflict with newer main versions |
| `fix/conveyor-asset-hardlink-custody-20261102` | `0a04044c63` | 2026-11-05 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/conveyor-automerge-preflight-evidence-review-gates-20261103` | `82afac5f62` | 2026-11-05 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/conveyor-backend-quality-timeout-20261102` | `d1c7102213` | 2026-11-02 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/conveyor-changelog-markdown-evidence-20261102` | `c889800416` | 2026-11-03 | nothing unique | superseded: its 14 remaining edits conflict with newer main versions |
| `fix/conveyor-config-json-duplicate-key-guard-20261102` | `90fd437a5b` | 2026-11-09 | fully on main | every changed blob already on main |
| `fix/conveyor-delivery-cli-descriptor-tree-20261102` | `0528ebeb7d` | 2026-11-03 | nothing unique | superseded: its 14 remaining edits conflict with newer main versions |
| `fix/conveyor-delivery-path-control-guard-20261102` | `b735f036a9` | 2026-11-05 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. skeleton/testing/test_delivery_path_controls.py |
| `fix/conveyor-delivery-secret-scan-boundaries-20261102` | `56252b8ca5` | 2026-11-03 | nothing unique | superseded: its 14 remaining edits conflict with newer main versions |
| `fix/conveyor-deploy-bake-strategy-validation-20261102` | `e13445f574` | 2026-11-03 | nothing unique | superseded: its 14 remaining edits conflict with newer main versions |
| `fix/conveyor-deploy-window-clock-validation-20261102` | `b1fdd0d4f8` | 2026-11-05 | nothing unique | superseded: its 20 remaining edits conflict with newer main versions |
| `fix/conveyor-embedding-evidence-overlap-20261107` | `052321f6fe` | 2026-11-09 | fully on main | every changed blob already on main |
| `fix/conveyor-farm-attestation-uniqueness-20261102` | `d4c830ee6e` | 2026-11-09 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/conveyor-frontend-implicit-compose-fence-20261103` | `bb7dc6d36b` | 2026-11-03 | unique content pending port | 0 new files, 2 modified files survive a 3-way merge |
| `fix/conveyor-health-observation-admission-20261102` | `61cb3fccc7` | 2026-11-05 | nothing unique | superseded: its 29 remaining edits conflict with newer main versions |
| `fix/conveyor-main-python-syntax-20261105` | `2c418864a4` | 2026-11-05 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/conveyor-mod-resolver-bounds-20261102` | `2dfbaf5607` | 2026-11-05 | fully on main | every changed blob already on main |
| `fix/conveyor-promotion-evidence-identity-20261102` | `32cbe6e466` | 2026-11-03 | nothing unique | superseded: its 14 remaining edits conflict with newer main versions |
| `fix/conveyor-release-commit-provenance-20261102` | `04102951bf` | 2026-11-05 | nothing unique | superseded: its 41 remaining edits conflict with newer main versions |
| `fix/conveyor-release-history-record-validation-20261102` | `1bf1d32b6b` | 2026-11-03 | nothing unique | superseded: its 14 remaining edits conflict with newer main versions |
| `fix/conveyor-remote-receipt-reconciliation-20261102` | `f1d9d03a7f` | 2026-11-09 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `fix/conveyor-sbom-dependency-completeness-20261102` | `1166848ca8` | 2026-11-05 | nothing unique | superseded: its 38 remaining edits conflict with newer main versions |
| `fix/conveyor-semver-resource-boundaries-20261102` | `766f4e9b45` | 2026-11-05 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. skeleton/testing/test_delivery_path_controls.py |
| `fix/conveyor-shared-python314-architecture-mirror-20261108-r01` | `b4ef7d3e45` | 2026-11-10 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/conveyor-smoke-evidence-integrity-20261102` | `4088cb5447` | 2026-11-03 | nothing unique | superseded: its 14 remaining edits conflict with newer main versions |
| `fix/conveyor-supervisor-model-config-preflight-20261103` | `a8a5544c6d` | 2026-11-05 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/coordinated-ruff-017-toolchain-20261020` | `0258725e6a` | 2026-10-20 | nothing unique | superseded: its 9 remaining edits conflict with newer main versions |
| `fix/core-package-metadata-parity-20261026` | `5eb62f569e` | 2026-10-26 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `fix/cortex-guard-included-routers` | `196398932f` | 2026-10-17 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `fix/cost-governor-estimate-overrun-20261030` | `45aa8f67e1` | 2026-10-30 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/cost-governor-replay-reattach-test-20261030` | `6e6552ba6b` | 2026-10-30 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/dependabot-split-expo-native-navigation-20261026` | `3742c2659a` | 2026-10-26 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/devops-restore-ci-gates-4104` | `7daafebb23` | 2026-10-19 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/devops-ruff-provider-gate-timeout` | `71c4afed97` | 2026-10-17 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `fix/devops-unit-required-4131` | `65d62298f4` | 2026-10-25 | unique content pending port | 0 new files, 6 modified files survive a 3-way merge |
| `fix/discourse-admission-public-error-redaction-20261110-r01` | `6fa610a05d` | 2026-11-10 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/discourse-canonical-model-dispatch-20261105` | `8e9ed5f330` | 2026-11-09 | ported in PR #5771 | all 0 new / 1 modified surviving paths are carried by the port |
| `fix/discourse-identity-and-catalog-preflight-20261111-r01` | `f871ec4303` | 2026-11-11 | nothing unique | superseded: its 18 remaining edits conflict with newer main versions |
| `fix/discourse-judge-admission-20261105` | `8d6bd2d6d7` | 2026-11-09 | nothing unique | superseded: its 5 remaining edits conflict with newer main versions |
| `fix/discourse-panel-malformed-input-failclosed-20261111-r01` | `433eb77ab5` | 2026-11-11 | nothing unique | superseded: its 20 remaining edits conflict with newer main versions |
| `fix/discourse-preflight-engine-before-io-20261111-r01` | `31d4e558de` | 2026-11-11 | nothing unique | superseded: its 20 remaining edits conflict with newer main versions |
| `fix/discourse-receipt-and-judge-binding-20261111-r01` | `bea74f4e07` | 2026-11-11 | nothing unique | superseded: its 19 remaining edits conflict with newer main versions |
| `fix/discourse-tenant-owned-custody-20261105` | `d3e10f919a` | 2026-11-09 | ported in PR #5771 | all 0 new / 1 modified surviving paths are carried by the port |
| `fix/discourse-tenant-route-20261111-0631` | `4db76ab895` | 2026-11-11 | nothing unique | superseded: its 15 remaining edits conflict with newer main versions |
| `fix/discourse-terminal-receipt-bounds-20261111-r1` | `c80e3fd239` | 2026-11-11 | fully on main | every changed blob already on main |
| `fix/docker-heredoc-custody-20261115-r01` | `5843353b09` | 2026-11-15 | fully on main | every changed blob already on main |
| `fix/docker-local-ai-chroma-dirfd-index-race-20261120-r01` | `8293974ae9` | 2026-11-20 | unique content pending port | 104 new files, 25 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5724 (mergeable) -> feat/docker-local-ai-chroma-index-custody-20261120-r01; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `fix/docker-local-ai-chroma-dirfd-index-race-ci-20261120-r01` | `8293974ae9` | 2026-11-20 | unique content pending port | 104 new files, 25 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5725 (conflicting) -> main; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `fix/docker-local-ai-mongo-real-quorum-semantics-20261120-r01` | `afda3b7e78` | 2026-11-20 | unique content pending port | 86 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5707 (mergeable) -> feat/docker-local-ai-minority-fencing-20261120-r01; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `fix/docker-local-ai-mongo-real-quorum-semantics-ci-20261120-r01` | `afda3b7e78` | 2026-11-20 | unique content pending port | 86 new files, 24 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5708 (conflicting) -> main; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `fix/docker-local-ai-mongo-restore-root-dirfd-20261120-r01` | `ada31d479b` | 2026-11-20 | unique content pending port | 113 new files, 25 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5732 (mergeable) -> feat/docker-local-ai-mongo-wiredtiger-custody-20261120-r01; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `fix/docker-local-ai-mongo-restore-root-dirfd-ci-20261120-r01` | `ada31d479b` | 2026-11-20 | unique content pending port | 113 new files, 25 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5733 (conflicting) -> main; e.g. backend/core/local_guarded_epoch_startup.py, backend/tests/test_galaxy_authoring_source_api.py, backend/tests/test_local_guarded_epoch_startup.py |
| `fix/domain-cli-restore-20261109` | `ece8a0c9dd` | 2026-11-09 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/domain-offline-suites-20261109` | `b0815bd817` | 2026-11-10 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/dragon-delivery-exception-custody-20261024` | `a116079ccb` | 2026-11-13 | fully on main | every changed blob already on main |
| `fix/dragon-state-traceability-20261023` | `88c59bda00` | 2026-11-13 | fully on main | every changed blob already on main |
| `fix/dragon-three-reusable-exact-head-ci-budget-20261109` | `e5bcee09bb` | 2026-11-13 | fully on main | every changed blob already on main |
| `fix/e2e-live-proof-20261110-r02` | `8c627d6b29` | 2026-11-11 | unique content pending port | 12 new files, 54 modified files survive a 3-way merge; 1 paths already carried by port PRs; e.g. skeleton/testing/test_game_project_cli_custody.py, skeleton/testing/test_game_project_cli_input_budget.py, skeleton/testing/test_godot_export_cli_custody.py |
| `fix/e2e-mainline-source-convergence-20261110-r01` | `384e18db0f` | 2026-11-10 | nothing unique | superseded: its 7 remaining edits conflict with newer main versions |
| `fix/ecosystem-response-boundary-20261030` | `8a780294e9` | 2026-10-30 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `fix/emerald-device-admission-preflight-20261117` | `5f71e350dc` | 2026-11-17 | unique content pending port | 34 new files, 6 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5512 (mergeable) -> fix/emerald-typecheck-and-qualification-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, artifacts/emerald/.gitignore, docs/DRAGON_ATELIER_INSPECTION_LAB.md |
| `fix/emerald-evolution-exact-head-ci-20261117` | `d452bd3b07` | 2026-11-17 | unique content pending port | 75 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5549 (conflicting) -> feat/emerald-weighted-developmental-evolutions-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, artifacts/emerald/.gitignore |
| `fix/emerald-exact-asset-recovery-20261117` | `1d4e45e584` | 2026-11-17 | unique content pending port | 48 new files, 6 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5517 (mergeable) -> feat/emerald-native-material-audit-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, artifacts/emerald/.gitignore, docs/DRAGON_ATELIER_INSPECTION_LAB.md |
| `fix/emerald-final-forge-roundtrip-20261117` | `8e04c467d3` | 2026-11-17 | unique content pending port | 60 new files, 14 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5525 (mergeable) -> feat/emerald-lfs-transfer-custody-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, artifacts/emerald/.gitignore, docs/DRAGON_ATELIER_INSPECTION_LAB.md |
| `fix/emerald-forge-native-qualification-20261117` | `a5ad1537fc` | 2026-11-17 | unique content pending port | 51 new files, 14 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5520 (mergeable) -> fix/emerald-render-residency-and-fallback-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, artifacts/emerald/.gitignore, docs/DRAGON_ATELIER_INSPECTION_LAB.md |
| `fix/emerald-inherited-forge-provenance-20261117` | `a7c50f9baf` | 2026-11-17 | unique content pending port | 60 new files, 9 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5529 (mergeable) -> feat/emerald-native-staging-verifier-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, artifacts/emerald/.gitignore, docs/DRAGON_ATELIER_INSPECTION_LAB.md |
| `fix/emerald-inherited-forge-ssr-custody-20261117` | `a6eddeabdb` | 2026-11-17 | unique content pending port | 60 new files, 13 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5530 (mergeable) -> fix/emerald-inherited-forge-provenance-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, artifacts/emerald/.gitignore, docs/DRAGON_ATELIER_INSPECTION_LAB.md |
| `fix/emerald-native-web-staging-custody-20261117` | `56d973da62` | 2026-11-17 | unique content pending port | 49 new files, 6 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5518 (mergeable) -> fix/emerald-exact-asset-recovery-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, artifacts/emerald/.gitignore, docs/DRAGON_ATELIER_INSPECTION_LAB.md |
| `fix/emerald-original-binary-recovered-20261117` | `0d7938e7d8` | 2026-11-17 | unique content pending port | 57 new files, 14 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5522 (mergeable) -> fix/emerald-forge-native-qualification-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, artifacts/emerald/.gitignore, docs/DRAGON_ATELIER_INSPECTION_LAB.md |
| `fix/emerald-recovered-archive-qualification-20261117` | `22fffa4a9b` | 2026-11-17 | unique content pending port | 53 new files, 6 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5521 (mergeable) -> fix/emerald-render-residency-and-fallback-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, artifacts/emerald/.gitignore, docs/DRAGON_ATELIER_INSPECTION_LAB.md |
| `fix/emerald-render-residency-and-fallback-20261117` | `1a4f7d47a1` | 2026-11-17 | unique content pending port | 50 new files, 6 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5519 (mergeable) -> fix/emerald-native-web-staging-custody-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, artifacts/emerald/.gitignore, docs/DRAGON_ATELIER_INSPECTION_LAB.md |
| `fix/emerald-shared-source-gates-20261117` | `0d23e1fa1e` | 2026-11-20 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge; open PR #5509 (conflicting) -> main |
| `fix/emerald-typecheck-and-qualification-20261117` | `6f455fd98c` | 2026-11-17 | unique content pending port | 30 new files, 6 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5511 (mergeable) -> reconcile/emerald-peak-unified-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, artifacts/emerald/.gitignore, docs/DRAGON_ATELIER_INSPECTION_LAB.md |
| `fix/emerald-v4-provisional-motion-hold-20261117` | `b8a91190fe` | 2026-11-17 | unique content pending port | 94 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5558 (mergeable) -> feat/emerald-v4-triangle-contact-gate-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `fix/emerald-v7-nine-phase-report-contract-20261117` | `942087fdc8` | 2026-11-17 | unique content pending port | 157 new files, 11 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5585 (mergeable) -> feat/emerald-v7-nine-phase-qualification-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `fix/emerald-v7-original-scene-palette-20261118` | `8304d8e87e` | 2026-11-18 | unique content pending port | 206 new files, 12 modified files survive a 3-way merge; 1 paths already carried by port PRs; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `fix/emerald-v7-real-mixer-process-custody-20261118` | `b5df91563f` | 2026-11-18 | unique content pending port | 201 new files, 12 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5616 (mergeable) -> feat/emerald-v7-three-execution-conveyor-20261118; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `fix/emerald-v7-registered-ci-gates-20261117` | `b560b9da98` | 2026-11-17 | unique content pending port | 162 new files, 12 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5587 (mergeable) -> feat/emerald-v7-reviewed-contact-toolchain-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `fix/emulator-audio-savestate-fixture-20261030` | `1e0a5c9f6c` | 2026-10-30 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/engine-authority-transport-20261105` | `c24daae5d6` | 2026-11-09 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/engine-fixture-provider-selection-20261023` | `427065e59a` | 2026-10-23 | nothing unique | superseded: its 5 remaining edits conflict with newer main versions |
| `fix/engine-handoff-inventory-headers-20261017` | `e2bf520fb6` | 2026-10-17 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `fix/engine-handoff-test-support-4131` | `56bcb62ced` | 2026-10-18 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `fix/engine-supervision-fault-custody-20261023` | `cf76d8b4d4` | 2026-10-23 | fully on main | every changed blob already on main |
| `fix/engine-text-identity-framing-20261105` | `92c9e4f897` | 2026-11-09 | fully on main | every changed blob already on main |
| `fix/engine-text-route-error-contract-20261110-r01` | `a77352f1f7` | 2026-11-10 | fully on main | every changed blob already on main |
| `fix/engine-transport-origin-proxy-custody-20261105` | `a4111cedff` | 2026-11-09 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/explicit-ci-trigger-inventory-20261106` | `465cdc5f00` | 2026-11-09 | unique content pending port | 2 new files, 4 modified files survive a 3-way merge; e.g. skeleton/testing/test_jeeves_desktop_request_deadline_fence.py, tests/test_ai_tree_source_pins.py |
| `fix/expo-cli-5428-static-patch-20261026` | `9aedc1211c` | 2026-10-26 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `fix/expo-cli-lockfile-preflight-20261026` | `d1df703a89` | 2026-10-26 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/expo-export-content-evidence-20261111-r01` | `851fb92766` | 2026-11-11 | nothing unique | superseded: its 22 remaining edits conflict with newer main versions |
| `fix/expo-marker-stream-isolation-20261111-r01` | `198b36a735` | 2026-11-11 | nothing unique | superseded: its 21 remaining edits conflict with newer main versions |
| `fix/expo-native-duplicate-dependency-preflight-20261026` | `c649480850` | 2026-10-26 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/expo-native-shadowed-pin-regression-20261026` | `5e226dc5b9` | 2026-10-26 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/expo-static-export-post-marker-lifecycle-20261110-r01` | `c2b7ae7a15` | 2026-11-10 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `fix/expo-static-patch-idempotency-20261026` | `e1cfbe2420` | 2026-10-26 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/external-api-egress-resource-custody-20261115-r01` | `568ffc654b` | 2026-11-16 | fully on main | every changed blob already on main |
| `fix/fail-closed-local-provider-activation-20261028` | `6ad90a2da1` | 2026-10-28 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `fix/failclosed-data-corpus-admission-20261016` | `80bd9df83c` | 2026-10-16 | fully on main | every changed blob already on main |
| `fix/feature-runner-test-explicit-timeout-20261024` | `dd34761f0f` | 2026-10-24 | fully on main | every changed blob already on main |
| `fix/first-install-ai-chat-prototype-20261112` | `482913eb42` | 2026-11-14 | unique content pending port | 0 new files, 2 modified files survive a 3-way merge |
| `fix/first-install-architecture-and-syntax-20261107` | `c00bf7b9d0` | 2026-11-07 | nothing unique | superseded: its 9 remaining edits conflict with newer main versions |
| `fix/first-install-critical-api-routes-20261023` | `a1ffad8b80` | 2026-10-23 | nothing unique | superseded: its 6 remaining edits conflict with newer main versions |
| `fix/first-install-default-backend-route-20261105` | `5586330e3d` | 2026-11-09 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/first-install-dynamic-cors-origin-20261105` | `f238f144bc` | 2026-11-09 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/first-install-full-qualification-20261106` | `38d4713149` | 2026-11-11 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/first-install-health-probe-no-redirect-20261105` | `e3ea4a3205` | 2026-11-09 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/first-install-integrated-recovery-20261105` | `bb15b453c8` | 2026-11-11 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `fix/first-install-native-fixtures-portable-20261105` | `55577357f7` | 2026-11-06 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `fix/first-install-route-registry-size-20261026` | `c1af3961b5` | 2026-10-26 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/first-install-source-inode-20261106` | `2adfca2fa3` | 2026-11-09 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `fix/flgb-backlog-evidence-static-custody-20261016` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `fix/flgb-backlog-verified-lint-20261016` | `5a81c71fc3` | 2026-10-18 | unique content pending port | 2 new files, 1 modified files survive a 3-way merge; e.g. .github/workflows/regression-gates-restore.yml, machine/current_task_solutions_draft.md |
| `fix/flgb-delegated-owner-analysis-20261016` | `e4d25f5543` | 2026-10-16 | fully on main | every changed blob already on main |
| `fix/formal-methods-loaded-module-only-20261026` | `dbe043e7d3` | 2026-10-26 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/free-api-dns-pin-test-contract-20261110-r01` | `c5199a58bb` | 2026-11-10 | fully on main | every changed blob already on main |
| `fix/free-api-pinned-public-dns-20261105` | `7fddedd0fd` | 2026-11-09 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/frontend-advisory-lock-custody-20261016` | `95604f7b86` | 2026-10-16 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `fix/frontend-auth-transport-security-20261028` | `85301a9a10` | 2026-10-28 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `fix/full-backlog-status-20261105` | `f4ffacb8c3` | 2026-11-05 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. docs/ops/FULL_BACKLOG_STATUS_2026-11-05.md |
| `fix/full-backlog-status-v2-20261105` | `fb897ec2c8` | 2026-11-05 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. docs/ops/FULL_BACKLOG_STATUS_V2_2026-11-05.md |
| `fix/full-backlog-status-v3-20261105` | `8358fc59eb` | 2026-11-05 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. docs/ops/FULL_BACKLOG_STATUS_V3_2026-11-05.md |
| `fix/full-backlog-status-v4-20261105` | `184ee8fd01` | 2026-11-05 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. docs/ops/FULL_BACKLOG_STATUS_V4_2026-11-05.md |
| `fix/full-backlog-status-v5-20261105` | `b39db71ce2` | 2026-11-05 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. docs/ops/FULL_BACKLOG_STATUS_V5_2026-11-05.md |
| `fix/full-backlog-status-v6-20261105` | `23ca0bb82c` | 2026-11-05 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. docs/ops/FULL_BACKLOG_STATUS_V6_2026-11-05.md |
| `fix/full-backlog-status-v7-20261105` | `45c6336b5c` | 2026-11-05 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. docs/ops/FULL_BACKLOG_STATUS_V7_2026-11-05.md |
| `fix/full-backlog-status-v8-20261105` | `5b539a3882` | 2026-11-05 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. docs/ops/FULL_BACKLOG_STATUS_V8_2026-11-05.md |
| `fix/full-backlog-status-v9-20261105` | `b94854567a` | 2026-11-05 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. docs/ops/FULL_BACKLOG_STATUS_V9_2026-11-05.md |
| `fix/functional-ai-creation-clock-20261026` | `bba30458cd` | 2026-10-26 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/galaxy-build-budget-truthful-completion-20261110-r01` | `69bf56edd2` | 2026-11-10 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/game-original-pcm-sfx-prefix-20261031-conveyor` | `e3293ee8fc` | 2026-11-05 | fully on main | every changed blob already on main |
| `fix/game-studio-release-schema-compat-20261108` | `c13e5944be` | 2026-11-09 | nothing unique | superseded: its 5 remaining edits conflict with newer main versions |
| `fix/game-verifier-preserve-boundary-errors-20261107-b` | `d1c1488d55` | 2026-11-07 | unique content pending port | 1 new files, 2 modified files survive a 3-way merge; e.g. .github/workflows/jeeves-offline-game-custody-qualification.yml |
| `fix/gameforge-bool-preflight-20261026` | `811f1248b2` | 2026-10-26 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/gameforge-build-readonly-boot-20261025` | `b582193e42` | 2026-10-26 | nothing unique | superseded: its 6 remaining edits conflict with newer main versions |
| `fix/gameforge-full-argument-preflight-20261026` | `bec710777b` | 2026-10-26 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/gameforge-quality-source-custody-20261115-r01` | `c9814c5bac` | 2026-11-16 | fully on main | every changed blob already on main |
| `fix/gauss-legendre-final-root-weights-20261026` | `4474c92cfe` | 2026-10-26 | fully on main | every changed blob already on main |
| `fix/godot-anchored-provenance-tree-20261110-r01` | `5a47737956` | 2026-11-10 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `fix/godot-mainline-provenance-convergence-20261110-r01` | `9cc4b84313` | 2026-11-11 | nothing unique | superseded: its 20 remaining edits conflict with newer main versions |
| `fix/harbor-patrol-cli-dispatch-20261111` | `1b837a4e32` | 2026-11-11 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/inference-payload-canonical-key-integrity-20261026` | `e074b8e4ab` | 2026-10-26 | fully on main | every changed blob already on main |
| `fix/installer-source-inode-epoch-20261106` | `4098168589` | 2026-11-06 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `fix/integration-discourse-observation-identity-20261111-r01` | `7fa09ba11d` | 2026-11-11 | nothing unique | superseded: its 24 remaining edits conflict with newer main versions |
| `fix/integration-expo-discourse-source-convergence-20261111-r01` | `3c1e443901` | 2026-11-11 | nothing unique | superseded: its 19 remaining edits conflict with newer main versions |
| `fix/integration-jeeves-canonical-preflight-20261111-r01` | `e1fc376ce9` | 2026-11-11 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/integration-native-batch-admission-clock-20261111-r01` | `4a47afea82` | 2026-11-11 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/issue-4133-private-git-workspaces-20261025` | `c88f1492f9` | 2026-10-25 | fully on main | every changed blob already on main |
| `fix/jeeves-258-canonical-ai-mirror-parity-20261104-r45` | `ccd392eaff` | 2026-11-05 | nothing unique | superseded: its 159 remaining edits conflict with newer main versions |
| `fix/jeeves-architecture-and-signed-audit-syntax-20261107` | `ae6efba6d2` | 2026-11-09 | unique content pending port | 1 new files, 2 modified files survive a 3-way merge; e.g. .github/workflows/jeeves-offline-game-custody-qualification.yml |
| `fix/jeeves-bounded-source-verified-cli-disclosure-20261104-r44` | `669117e399` | 2026-11-05 | nothing unique | superseded: its 154 remaining edits conflict with newer main versions |
| `fix/jeeves-canonical-mirror-ci-repair-20261104-r43` | `1ee7223c09` | 2026-11-05 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. skeleton/testing/test_jeeves_native_cli_output_custody.py |
| `fix/jeeves-chat-history-total-utf8-limit-20261104-r41` | `b1f98ade67` | 2026-11-05 | nothing unique | superseded: its 153 remaining edits conflict with newer main versions |
| `fix/jeeves-chat-linearizable-custody-20261104-r30` | `503b718dc6` | 2026-11-05 | nothing unique | superseded: its 169 remaining edits conflict with newer main versions |
| `fix/jeeves-chat-source-fenced-lifecycle-20261104-r31` | `ab333ef110` | 2026-11-05 | nothing unique | superseded: its 168 remaining edits conflict with newer main versions |
| `fix/jeeves-desktop-child-env-custody-20261105` | `8358888719` | 2026-11-09 | fully on main | every changed blob already on main |
| `fix/jeeves-desktop-completed-source-acceptance-20261104-r58` | `c9c60613cb` | 2026-11-05 | nothing unique | superseded: its 152 remaining edits conflict with newer main versions |
| `fix/jeeves-desktop-integrated-source-qualification-20261105` | `4ec2ab5a6d` | 2026-11-09 | unique content pending port | 4 new files, 1 modified files survive a 3-way merge; e.g. machine/jeeves_source_ci_trigger_registry.json, scripts/check_jeeves_source_ci_scope.py, skeleton/testing/test_jeeves_desktop_request_deadline_fence.py |
| `fix/jeeves-desktop-ipc-finite-frames-20261105` | `c02f2f2dfa` | 2026-11-09 | fully on main | every changed blob already on main |
| `fix/jeeves-desktop-launch-admission-20261105` | `cd170a4d7a` | 2026-11-09 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/jeeves-desktop-native-request-custody-timeout-20261104-r55` | `b32c868587` | 2026-11-05 | nothing unique | superseded: its 153 remaining edits conflict with newer main versions |
| `fix/jeeves-desktop-real-path-context-and-fixture-contracts-20261104-r65` | `9673049dc2` | 2026-11-05 | nothing unique | superseded: its 154 remaining edits conflict with newer main versions |
| `fix/jeeves-desktop-request-deadline-fence-20261105` | `dc6839befd` | 2026-11-09 | unique content pending port | 4 new files, 1 modified files survive a 3-way merge; e.g. machine/jeeves_source_ci_trigger_registry.json, scripts/check_jeeves_source_ci_scope.py, skeleton/testing/test_jeeves_desktop_request_deadline_fence.py |
| `fix/jeeves-desktop-source-contract-finalization-20261104-r67` | `2fee5bbe22` | 2026-11-05 | nothing unique | superseded: its 151 remaining edits conflict with newer main versions |
| `fix/jeeves-developer-mirror-parity-20261016` | `37084c34b0` | 2026-10-16 | nothing unique | superseded: its 22 remaining edits conflict with newer main versions |
| `fix/jeeves-durable-batch-source-syntax-20261104-r68` | `a7f3acc4d7` | 2026-11-05 | nothing unique | superseded: its 150 remaining edits conflict with newer main versions |
| `fix/jeeves-explicit-read-only-native-source-context-20261104-r74` | `03964bda4d` | 2026-11-05 | nothing unique | superseded: its 155 remaining edits conflict with newer main versions |
| `fix/jeeves-firstboot-security-integration-20261106` | `30e323ff0a` | 2026-11-06 | unique content pending port | 2 new files, 3 modified files survive a 3-way merge; e.g. skeleton/testing/test_jeeves_desktop_request_deadline_fence.py, tests/test_ai_tree_source_pins.py |
| `fix/jeeves-full-ci-domain-boundary-and-evidence-20261104-r47` | `2570d70fc8` | 2026-11-05 | nothing unique | superseded: its 156 remaining edits conflict with newer main versions |
| `fix/jeeves-full-ci-portable-sqlite-and-tree-index-20261104-r46` | `334e67263b` | 2026-11-05 | nothing unique | superseded: its 157 remaining edits conflict with newer main versions |
| `fix/jeeves-game-cli-mirror-parity-20261016` | `597d7d5dbf` | 2026-10-16 | nothing unique | superseded: its 21 remaining edits conflict with newer main versions |
| `fix/jeeves-integrate-architecture-evidence-ci-20261104-r50` | `ba3725f11f` | 2026-11-05 | nothing unique | superseded: its 141 remaining edits conflict with newer main versions |
| `fix/jeeves-literal-laptop-registry-20261111-r01` | `38390497b1` | 2026-11-11 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/jeeves-live-gguf-source-fence-20261104-r28` | `da1562aa3b` | 2026-11-04 | nothing unique | superseded: its 172 remaining edits conflict with newer main versions |
| `fix/jeeves-mirror-native-qualification-integration-20261107` | `c00bf7b9d0` | 2026-11-07 | nothing unique | superseded: its 9 remaining edits conflict with newer main versions |
| `fix/jeeves-monotonic-live-source-revocation-20261104-r32` | `dbb2ca6e3b` | 2026-11-05 | nothing unique | superseded: its 168 remaining edits conflict with newer main versions |
| `fix/jeeves-native-bounded-attempt-custody-20261104` | `d1973ce1c9` | 2026-11-04 | nothing unique | superseded: its 168 remaining edits conflict with newer main versions |
| `fix/jeeves-native-chat-commit-hold-contract-20261104-r16` | `b444d0211a` | 2026-11-05 | nothing unique | superseded: its 176 remaining edits conflict with newer main versions |
| `fix/jeeves-native-chat-identity-and-history-fence-20261104` | `24f37252be` | 2026-11-05 | nothing unique | superseded: its 173 remaining edits conflict with newer main versions |
| `fix/jeeves-native-chat-postread-race-fences-20261104` | `5f635f3574` | 2026-11-05 | unique content pending port | 3 new files, 0 modified files survive a 3-way merge; e.g. skeleton/testing/test_jeeves_operator_postio_epoch_start.py, skeleton/testing/test_jeeves_operator_postio_failure_custody.py, skeleton/testing/test_jeeves_operator_postio_private_replay.py |
| `fix/jeeves-native-chat-serialized-custody-20261104` | `1e71eaf712` | 2026-11-04 | unique content pending port | 3 new files, 0 modified files survive a 3-way merge; e.g. skeleton/testing/test_jeeves_operator_postio_epoch_start.py, skeleton/testing/test_jeeves_operator_postio_failure_custody.py, skeleton/testing/test_jeeves_operator_postio_private_replay.py |
| `fix/jeeves-native-cli-source-identity-timeout-20261104-r27` | `94d8b0be17` | 2026-11-05 | nothing unique | superseded: its 172 remaining edits conflict with newer main versions |
| `fix/jeeves-native-live-source-epoch-custody-20261104-r29` | `5fe48e5a7c` | 2026-11-04 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. skeleton/jeeves/agent/native_source_epoch.py |
| `fix/jeeves-native-preflight-resource-admission-20261104` | `40605a5a13` | 2026-11-04 | nothing unique | superseded: its 168 remaining edits conflict with newer main versions |
| `fix/jeeves-native-principal-recheck-before-io-20261104` | `19229cfdb9` | 2026-11-05 | nothing unique | superseded: its 171 remaining edits conflict with newer main versions |
| `fix/jeeves-native-readiness-installed-gguf-authority-20261104-r28` | `a5ef61d473` | 2026-11-05 | nothing unique | superseded: its 168 remaining edits conflict with newer main versions |
| `fix/jeeves-native-readiness-no-synthetic-promotion-20261104-r29` | `da1562aa3b` | 2026-11-04 | nothing unique | superseded: its 172 remaining edits conflict with newer main versions |
| `fix/jeeves-native-repl-exact-utf8-framing-20261104-r33` | `7019f0abd5` | 2026-11-04 | nothing unique | superseded: its 168 remaining edits conflict with newer main versions |
| `fix/jeeves-native-singleflight-source-prompt-fixtures-20261104-r49` | `c17d2f6e89` | 2026-11-05 | nothing unique | superseded: its 141 remaining edits conflict with newer main versions |
| `fix/jeeves-operator-exclusive-stream-20261104-r38` | `dd60a6cca6` | 2026-11-05 | nothing unique | superseded: its 155 remaining edits conflict with newer main versions |
| `fix/jeeves-operator-jsonl-stream-custody-20261104-r37` | `c8a894e5e7` | 2026-11-04 | nothing unique | superseded: its 158 remaining edits conflict with newer main versions |
| `fix/jeeves-operator-session-final-result-identity-20261104` | `4ada238c20` | 2026-11-05 | unique content pending port | 3 new files, 0 modified files survive a 3-way merge; e.g. skeleton/testing/test_jeeves_operator_postio_epoch_start.py, skeleton/testing/test_jeeves_operator_postio_failure_custody.py, skeleton/testing/test_jeeves_operator_postio_private_replay.py |
| `fix/jeeves-private-escrow-preflight-path-contracts-20261105-r81` | `d73afe61b8` | 2026-11-05 | nothing unique | superseded: its 147 remaining edits conflict with newer main versions |
| `fix/jeeves-public-citation-authority-20261016` | `adaf187da0` | 2026-10-16 | nothing unique | superseded: its 20 remaining edits conflict with newer main versions |
| `fix/jeeves-quota-denial-without-session-mutation-20261104` | `3c7d77cca1` | 2026-11-05 | nothing unique | superseded: its 171 remaining edits conflict with newer main versions |
| `fix/jeeves-real-device-harness-source-custody-20261104-r51` | `53eb33f554` | 2026-11-04 | nothing unique | superseded: its 141 remaining edits conflict with newer main versions |
| `fix/jeeves-real-gguf-acceptance-boundary-20261104-r46` | `b50226967b` | 2026-11-04 | nothing unique | superseded: its 154 remaining edits conflict with newer main versions |
| `fix/jeeves-real-gguf-first-turn-cold-reopen-20261104-r46` | `0016655b5e` | 2026-11-05 | nothing unique | superseded: its 151 remaining edits conflict with newer main versions |
| `fix/jeeves-repl-single-stream-20261104-r42` | `3bb722c6d0` | 2026-11-04 | nothing unique | superseded: its 153 remaining edits conflict with newer main versions |
| `fix/jeeves-session-cli-preactivate-resources-20261104` | `65d4b36350` | 2026-11-05 | nothing unique | superseded: its 171 remaining edits conflict with newer main versions |
| `fix/jeeves-single-native-provider-attempt-ledger-20261104` | `aed887235f` | 2026-11-05 | nothing unique | superseded: its 171 remaining edits conflict with newer main versions |
| `fix/jeeves-single-shot-stdout-custody-20261104-r44` | `6c5dad8dc8` | 2026-11-04 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. skeleton/testing/test_jeeves_native_cli_output_custody.py |
| `fix/jeeves-source-fenced-native-batch-cli-20261104-r45` | `25b44a8e4c` | 2026-11-05 | nothing unique | superseded: its 154 remaining edits conflict with newer main versions |
| `fix/jeeves-sqlite-history-context-contract-20261104-r59` | `a74fda1976` | 2026-11-05 | nothing unique | superseded: its 154 remaining edits conflict with newer main versions |
| `fix/jeeves-startup-principal-private-root-admission-20261104-r35` | `f01e1998f6` | 2026-11-05 | nothing unique | superseded: its 158 remaining edits conflict with newer main versions |
| `fix/jeeves-stdlib-tomllib-20261113` | `c960d0af0d` | 2026-11-13 | fully on main | every changed blob already on main |
| `fix/jeeves-tts-bounded-narration-20261105` | `b06e0d522d` | 2026-11-09 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/jeeves-unified-installed-source-contract-20261104-r39` | `8d1527d67a` | 2026-11-05 | nothing unique | superseded: its 155 remaining edits conflict with newer main versions |
| `fix/jeeves-unified-native-live-source-20261104-r29` | `93bf7440ab` | 2026-11-05 | nothing unique | superseded: its 168 remaining edits conflict with newer main versions |
| `fix/land-parity-sync-parallel-scan-on-main-20261023` | `5ca8610198` | 2026-10-23 | fully on main | every changed blob already on main |
| `fix/laptop-bound-client-identity-and-receipt-20261104-r20` | `c5e72000a1` | 2026-11-05 | nothing unique | superseded: its 172 remaining edits conflict with newer main versions |
| `fix/laptop-bounded-native-inference-timeout-20261104-r26` | `a9e19c0c3e` | 2026-11-05 | nothing unique | superseded: its 171 remaining edits conflict with newer main versions |
| `fix/laptop-cold-reopen-full-principal-and-live-source-fence-20261104-r23` | `ab2f336998` | 2026-11-05 | nothing unique | superseded: its 174 remaining edits conflict with newer main versions |
| `fix/laptop-exact-stdin-and-expected-model-pins-20261104-r21` | `aa973a94de` | 2026-11-05 | nothing unique | superseded: its 175 remaining edits conflict with newer main versions |
| `fix/laptop-first-turn-postgeneration-source-witness-20261104-r24` | `c41777e41d` | 2026-11-04 | nothing unique | superseded: its 175 remaining edits conflict with newer main versions |
| `fix/laptop-first-turn-preflight-before-session-20261104-r17` | `e106478c15` | 2026-11-05 | nothing unique | superseded: its 175 remaining edits conflict with newer main versions |
| `fix/laptop-frontend-bootstrap-20261103` | `e9df35647b` | 2026-11-03 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `fix/laptop-native-http-dispatcher-singleflight-20261104-r12` | `5af8b8ecc4` | 2026-11-05 | nothing unique | superseded: its 175 remaining edits conflict with newer main versions |
| `fix/laptop-native-turnbridge-durable-receipt-epoch-20261104-r13` | `9869612bbb` | 2026-11-05 | nothing unique | superseded: its 175 remaining edits conflict with newer main versions |
| `fix/laptop-once-admission-before-sqlite-session-20261104` | `de186dfbd1` | 2026-11-05 | nothing unique | superseded: its 175 remaining edits conflict with newer main versions |
| `fix/laptop-real-acceptance-installed-receipt-20261104-r19` | `59117feb62` | 2026-11-05 | nothing unique | superseded: its 172 remaining edits conflict with newer main versions |
| `fix/laptop-testdouble-native-request-collision-20261104-r18` | `33481cd9e8` | 2026-11-05 | nothing unique | superseded: its 173 remaining edits conflict with newer main versions |
| `fix/legacy-chat-replay-digest-20261023` | `19b25f29b8` | 2026-10-23 | nothing unique | superseded: its 23 remaining edits conflict with newer main versions |
| `fix/living-world-checkpoint-canonical-b64-20261020` | `3b9004382f` | 2026-10-20 | fully on main | every changed blob already on main |
| `fix/llm-router-firstboot-bounded-config-20261105` | `18f2877712` | 2026-11-09 | fully on main | every changed blob already on main |
| `fix/load-shed-503-retry-evidence-20261025` | `32a7116c35` | 2026-10-25 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `fix/local-ai-client-cli-preflight-redaction-20261104` | `8ffc41f3b1` | 2026-11-05 | unique content pending port | 3 new files, 0 modified files survive a 3-way merge; e.g. skeleton/testing/test_jeeves_operator_postio_epoch_start.py, skeleton/testing/test_jeeves_operator_postio_failure_custody.py, skeleton/testing/test_jeeves_operator_postio_private_replay.py |
| `fix/local-ai-cold-reopen-live-stdout-20261104-r48` | `dad168d834` | 2026-11-05 | nothing unique | superseded: its 143 remaining edits conflict with newer main versions |
| `fix/local-ai-dispatcher-bound-sqlite-replay-20261104` | `f4ee263a71` | 2026-11-05 | unique content pending port | 3 new files, 0 modified files survive a 3-way merge; e.g. skeleton/testing/test_jeeves_operator_postio_epoch_start.py, skeleton/testing/test_jeeves_operator_postio_failure_custody.py, skeleton/testing/test_jeeves_operator_postio_private_replay.py |
| `fix/local-ai-hardware-governed-capacity-20261030` | `f684e6715a` | 2026-10-30 | unique content pending port | 0 new files, 2 modified files survive a 3-way merge |
| `fix/long-session-stability-lint-20261017` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `fix/main-backend-ci-test-contracts-20261025` | `2e7da7823e` | 2026-10-25 | unique content pending port | 0 new files, 2 modified files survive a 3-way merge |
| `fix/main-ci-green-20261109` | `09d783b453` | 2026-11-09 | nothing unique | superseded: its 12 remaining edits conflict with newer main versions |
| `fix/main-ci-immutable-concurrency-20261026` | `29b3840599` | 2026-10-26 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/main-galaxy-profile-custody-20261114` | `97436cdd22` | 2026-11-15 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `fix/main-recovery-gguf-ci-20261114` | `9c9316d742` | 2026-11-15 | unique content pending port | 0 new files, 22 modified files survive a 3-way merge; open PR #5349 (conflicting) -> main |
| `fix/malware-41454774141-regex-alternation` | `4699470f95` | 2026-11-05 | fully on main | every changed blob already on main |
| `fix/manual-owner-housekeeping-workflow-contract-20261110-r01` | `7e64aa74bd` | 2026-11-10 | fully on main | every changed blob already on main |
| `fix/manual-rebase-conflicts-20261105` | `019bd4afc4` | 2026-11-05 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. docs/ci/MANUAL_REBASE_CONFLICTS_2026-11-05.md |
| `fix/masterplan-manual-workflow-evidence-paths-20261023` | `4d5479874f` | 2026-10-23 | nothing unique | superseded: its 8 remaining edits conflict with newer main versions |
| `fix/merge-readiness-pymongo-pin-20261020` | `36241db475` | 2026-10-20 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/merge-readiness-pytest-namespace-collision-20261113` | `d9e9cbf69b` | 2026-11-14 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `fix/merge-readiness-ruff-expo-contract-20261027` | `742e99448d` | 2026-10-28 | unique content pending port | 0 new files, 33 modified files survive a 3-way merge |
| `fix/merge-unblock-ai-tree-parity-20261020` | `fa7c0e7f7b` | 2026-10-20 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `fix/motor-event-loop-rebind-20261018` | `b19538a431` | 2026-10-18 | fully on main | every changed blob already on main |
| `fix/native-five-portable-fixtures-20261108` | `d3f5c02b56` | 2026-11-09 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `fix/native-output-receipt-custody-20261106` | `96ced0936d` | 2026-11-09 | unique content pending port | 2 new files, 3 modified files survive a 3-way merge; e.g. skeleton/testing/test_jeeves_desktop_request_deadline_fence.py, tests/test_ai_tree_source_pins.py |
| `fix/native-qualification-verify-bounds-20261111-r01` | `55553b7b8d` | 2026-11-11 | nothing unique | superseded: its 23 remaining edits conflict with newer main versions |
| `fix/native-report-atomic-stage-20261111-r01` | `4487faa60b` | 2026-11-11 | nothing unique | superseded: its 22 remaining edits conflict with newer main versions |
| `fix/native-report-bounded-canonical-custody-20261111-r01` | `05b2c18c7b` | 2026-11-11 | nothing unique | superseded: its 23 remaining edits conflict with newer main versions |
| `fix/native-report-final-inode-verification-20261111-r01` | `818fa9defd` | 2026-11-11 | nothing unique | superseded: its 22 remaining edits conflict with newer main versions |
| `fix/native-report-preflight-json-chunks-20261111-r01` | `66a96ca423` | 2026-11-11 | nothing unique | superseded: its 22 remaining edits conflict with newer main versions |
| `fix/native-transformer-literal-lazy-import-20261026` | `006517b419` | 2026-10-26 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/next-rebase-notes-20261105` | `effe903cbb` | 2026-11-05 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. docs/ci/NEXT_REBASE_STATUS_2026-11-05.md |
| `fix/node-forge-rsa-install-custody-20261115-r01` | `f954f9c438` | 2026-11-19 | unique content pending port | 5 new files, 41 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5421 (conflicting) -> main; e.g. skeleton/ai/forge/original_native_modes.py, skeleton/forge/original_native_modes.py, skeleton/testing/test_native_candidate_oracle_inventory.py |
| `fix/obj-finite-metadata-rebase-20261105` | `cee013e7b8` | 2026-11-05 | unique content pending port | 2 new files, 1 modified files survive a 3-way merge; e.g. docs/assets/OBJ_FINITE_APPLIED.md, docs/assets/OBJ_FINITE_REBASE_2026-11-05.md |
| `fix/offline-cli-grounding-workspace-backups-20261026` | `7d2f62f6a7` | 2026-10-26 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/operational-ai-literal-dispatch-20261111-r01` | `449b59d5b9` | 2026-11-11 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/outstanding-backlog-sota-local-ai-20261022` | `cead1bdc29` | 2026-10-22 | unique content pending port | 4 new files, 0 modified files survive a 3-way merge; e.g. docs/OUTSTANDING_BACKLOG_FIXES.md, skeleton/cortex/seams/outstanding_backlog_sota.py, skeleton/forge/seams/outstanding_backlog_forge.py |
| `fix/package-normalized-duplicate-guard-20261026` | `2e3c55a637` | 2026-10-26 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/perf-frame-threshold-admission-20261111-r01` | `364a80f90a` | 2026-11-11 | nothing unique | superseded: its 21 remaining edits conflict with newer main versions |
| `fix/perf-profiler-preloaded-target-20261111-r01` | `d0dcbf3baf` | 2026-11-11 | nothing unique | superseded: its 20 remaining edits conflict with newer main versions |
| `fix/perf-script-bounded-deque-20261111-r01` | `acb00ac51d` | 2026-11-11 | nothing unique | superseded: its 20 remaining edits conflict with newer main versions |
| `fix/pin-four-workflow-actions-20261023` | `4704fb177d` | 2026-10-23 | nothing unique | superseded: its 19 remaining edits conflict with newer main versions |
| `fix/polynomial-root-deterministic-seed-20261026` | `5f9bdd4775` | 2026-10-26 | fully on main | every changed blob already on main |
| `fix/portable-filenames-20261016` | `02817535eb` | 2026-10-16 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `fix/portable-native-flight-mirror-custody-20261108` | `5dfc316d57` | 2026-11-08 | nothing unique | superseded: its 18 remaining edits conflict with newer main versions |
| `fix/postmerge-chat-replay-contract-20261023` | `5892b1cc5e` | 2026-10-23 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/postmerge-e2e-build-isolation-20261110-r01` | `76489201cc` | 2026-11-10 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/postmerge-runtime-replay-qualification-20261110-r02` | `c6cf1d9ab6` | 2026-11-10 | nothing unique | superseded: its 15 remaining edits conflict with newer main versions |
| `fix/postmerge-save-ancestor-descriptor-custody-20261110-r01` | `f61440c9a8` | 2026-11-10 | fully on main | every changed blob already on main |
| `fix/pr-merge-hold-required-check-20261111` | `2436fa49d7` | 2026-11-11 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `fix/prefab-and-scene-depth-integration-20261108` | `e4aec31ab5` | 2026-11-08 | unique content pending port | 14 new files, 3 modified files survive a 3-way merge; e.g. skeleton/testing/test_installer_contract_failure_receipts.py, skeleton/testing/test_installer_diagnostic_recovery.py, skeleton/testing/test_installer_setup_probe_custody.py |
| `fix/preinstall-backend-image-python-guard-20261105` | `4030b1b001` | 2026-11-09 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/process-safety-explicit-feature-test-subprocess-20261024` | `2bd872af23` | 2026-10-24 | fully on main | every changed blob already on main |
| `fix/product-surface-discourse-digest-20261113` | `201f256c53` | 2026-11-13 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/production-fabric-single-local-api-20261107` | `c38518bc32` | 2026-11-07 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/provenance-and-limits-20261016` | `59f52e2f57` | 2026-10-16 | unique content pending port | 0 new files, 2 modified files survive a 3-way merge |
| `fix/provenance-data-root-limit-20261016` | `51a1362327` | 2026-10-16 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `fix/provider-delta-aware-time-20261026` | `028fcae8c1` | 2026-10-26 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/public-env-loopback-credentials-20261105` | `e4043ab910` | 2026-11-09 | fully on main | every changed blob already on main |
| `fix/public-evidence-url-validation-20261016` | `2eb75d75f4` | 2026-10-16 | ported in PR #5779 |  |
| `fix/quality-automation-supported-dependency-floors-20261026` | `4177b522f2` | 2026-10-26 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `fix/quality-parity-ruff-0172-20261026` | `0ba231f00a` | 2026-10-26 | fully on main | every changed blob already on main |
| `fix/realtime-client-sealed-owner-fixtures-20261026` | `be1c872672` | 2026-10-26 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/rebase-conflict-notes-20261105` | `bb3865dc08` | 2026-11-05 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. docs/ci/REBASE_CONFLICTS_2026-11-05.md |
| `fix/reconcile-first-install-ci-baseline-20261108` | `0027b9d40f` | 2026-11-09 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `fix/recover-stacked-mirror-scan-pr4211-4212-20261023` | `ef4097c8f4` | 2026-10-23 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/regeneration-prepared-route-fixture-20261024` | `8728e92b20` | 2026-10-24 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/repo-machine-quality-root-placement-20261110-r01` | `53a6e827b2` | 2026-11-10 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/repository-admission-taxonomy-20261115-r01` | `6ae3751052` | 2026-11-15 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge; open PR #5415 (conflicting) -> main |
| `fix/required-source-lanes-recovery-20261115-r01` | `4cf8f15894` | 2026-11-15 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/restore-private-memory-boundaries-20261028` | `db4c5ee270` | 2026-10-28 | unique content pending port | 0 new files, 5 modified files survive a 3-way merge |
| `fix/restore-required-retrieval-integration-20261023` | `d2123f655d` | 2026-10-23 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/rooms-api-dns-pinning-20261105` | `f0205b72ae` | 2026-11-09 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `fix/root-extras-metadata-parity-20261026` | `4e8bdc5994` | 2026-10-26 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/root-jeeves-literal-lazy-dispatch-20261026` | `47a64009b0` | 2026-10-26 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/sandbox-guard-clean-history-20261025` | `c6484866d1` | 2026-10-26 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `fix/sandbox-resource-limits-standalone-20261026` | `94a7c04230` | 2026-10-26 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/sandbox-stdin-nonblocking-timeout-20261026` | `3d5e3dc4fc` | 2026-10-27 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/sandbox-stdin-preflight-20261026` | `6af87164a2` | 2026-10-26 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/satellite-ui-case-references-20261016` | `32f3c6780a` | 2026-10-16 | unique content pending port | 1 new files, 3 modified files survive a 3-way merge; e.g. .github/workflows/satellite-ui-qualification.yml |
| `fix/scene-market-rebase-20261105` | `f5aafb796f` | 2026-11-05 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. docs/game/SCENE_MARKET_REBASE_2026-11-05.md |
| `fix/security-audit-undici-deepmerge-20261028` | `db0ba18f4d` | 2026-10-28 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `fix/security-boundary-restack-20261028` | `3dc3a8ac5e` | 2026-10-28 | unique content pending port | 0 new files, 2 modified files survive a 3-way merge |
| `fix/security-inventory-canonical-20261028` | `9d0ef6d399` | 2026-10-28 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `fix/security-live-pr-hold-labels-20261111-r01` | `c89c0edb79` | 2026-11-11 | fully on main | every changed blob already on main |
| `fix/security-workflow-control-manual-20261017` | `33ce5dc734` | 2026-10-18 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/share-route-url-origin-security-20261028` | `0d61f2905e` | 2026-10-28 | unique content pending port | 0 new files, 2 modified files survive a 3-way merge |
| `fix/shared-ci-durable-oracles-20261116-r01` | `6bbe9804d5` | 2026-11-16 | unique content pending port | 0 new files, 9 modified files survive a 3-way merge; open PR #5485 (conflicting) -> main |
| `fix/shared-frontend-native-oracle-20261115-r01` | `f54ce10aa8` | 2026-11-19 | unique content pending port | 5 new files, 75 modified files survive a 3-way merge; 3 paths already carried by port PRs; open PR #5422 (conflicting) -> main; e.g. frontend/scripts/test-nginx-setup-routing.cjs, skeleton/testing/test_first_laptop_preflight_quarantine.py, skeleton/testing/test_flight_sota_quarantine.py |
| `fix/shared-native-oracle-backlog-20261116` | `5b138c2493` | 2026-11-17 | nothing unique | superseded: its 5 remaining edits conflict with newer main versions |
| `fix/simulated-plan-evidence-descriptor-20261026` | `8514ab17b2` | 2026-10-26 | fully on main | every changed blob already on main |
| `fix/snapshot-case-paths-20261016` | `7f5a2cbfa7` | 2026-10-16 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. satellites/branch-snapshots/portable-path-migrations.json |
| `fix/static-lazy-import-dispatch-20261025` | `4f92bd9db0` | 2026-10-28 | unique content pending port | 0 new files, 36 modified files survive a 3-way merge |
| `fix/storage-lazy-loader-vault-secure-fs-20261110-r01` | `c45f0c0bd7` | 2026-11-10 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/storage-lazy-telemetry-registry-20261113-r01` | `706cb1495d` | 2026-11-14 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/strict-replay-environment-custody-20261110-r01` | `e93ad3d334` | 2026-11-10 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `fix/studio-a-adventure-inventory-custody-20261109-r11` | `a5f8c1f04f` | 2026-11-09 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/studio-a-canon-operation-custody-20261106` | `099b05c734` | 2026-11-07 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `fix/studio-a-scene-graph-deep-chain-20261109-r12` | `15b8ba8ad2` | 2026-11-09 | fully on main | every changed blob already on main |
| `fix/studio-a-stale-review-compile-20261107-r02` | `c0ca912f0c` | 2026-11-09 | unique content pending port | 1 new files, 1 modified files survive a 3-way merge; e.g. .github/workflows/jeeves-atomic-review-regression.yml |
| `fix/studio-b-godot-runner-bounded-results-20261109-r06` | `426567b60e` | 2026-11-09 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/studio-c-fail-closed-gguf-qualification-20261108` | `17524ded6b` | 2026-11-08 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/studio-c-native-profile-finite-evidence-20261108` | `b84598cef1` | 2026-11-08 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/studio-c-production-dispatcher-identity-20261107` | `07d9ba7108` | 2026-11-07 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/studio-c-stream-event-type-fencing-20261108` | `b921bd2ca3` | 2026-11-09 | fully on main | every changed blob already on main |
| `fix/studio-d-complete-public-service-urls-20261104-r11` | `1ca493b78f` | 2026-11-06 | unique content pending port | 4 new files, 0 modified files survive a 3-way merge; e.g. skeleton/testing/test_assembly_topology_admission.py, skeleton/testing/test_private_runtime_env_admission.py, skeleton/testing/test_public_port_collision_admission.py |
| `fix/studio-d-cross-process-setup-custody-20261103-r11` | `b0d85171ed` | 2026-11-05 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/studio-d-diagnostic-recovery-20261107-r06` | `eee4d965a7` | 2026-11-07 | unique content pending port | 5 new files, 0 modified files survive a 3-way merge; e.g. skeleton/testing/test_installer_contract_failure_receipts.py, skeleton/testing/test_installer_diagnostic_recovery.py, skeleton/testing/test_installer_setup_probe_custody.py |
| `fix/studio-d-doctor-proxy-isolation-20261109-0446` | `c149ca1bca` | 2026-11-09 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/studio-d-first-install-same-origin-20261108` | `014b5d4ccc` | 2026-11-08 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/studio-d-first-playable-rebase-20261105` | `9ad1057034` | 2026-11-05 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. docs/studio/STUDIO_D_FIRST_PLAYABLE_REBASE_2026-11-05.md |
| `fix/studio-d-first-run-probe-gate-20261107-r05` | `ec391cbc46` | 2026-11-10 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/studio-d-installer-caller-password-path-20261106-r08` | `7b7871062e` | 2026-11-06 | unique content pending port | 1 new files, 1 modified files survive a 3-way merge; e.g. skeleton/testing/test_installer_caller_password_path.py |
| `fix/studio-d-offline-kit-private-wheel-snapshot-20261031-r06` | `d330a34a25` | 2026-11-05 | fully on main | every changed blob already on main |
| `fix/studio-d-private-token-inode-20261107-v6` | `f3ea1b0172` | 2026-11-09 | fully on main | every changed blob already on main |
| `fix/studio-d-public-service-defaults-20261105-r12` | `3e9accda32` | 2026-11-06 | unique content pending port | 1 new files, 1 modified files survive a 3-way merge; e.g. skeleton/testing/test_public_service_defaults.py |
| `fix/studio-d-windows-setup-open-20261103-r11` | `4dd3318d09` | 2026-11-05 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/studio-encounters-reachable-terminal-defeat-20261030` | `5e25378551` | 2026-10-30 | ported in PR #5767 | all 68 new / 0 modified surviving paths are carried by the port (15 test modules held: fail on source branch too) |
| `fix/studio-hashed-replay-bound-leases-20261030` | `f616fd2c8a` | 2026-10-30 | ported in PR #5767 | all 35 new / 0 modified surviving paths are carried by the port (1 test modules held: fail on source branch too) |
| `fix/studio-immutable-eight-section-fence-20261030` | `10925447a9` | 2026-10-30 | ported in PR #5767 | all 33 new / 0 modified surviving paths are carried by the port (1 test modules held: fail on source branch too) |
| `fix/studio-object-durable-commit-20261030` | `fa2fe2e47b` | 2026-10-30 | ported in PR #5767 | all 40 new / 0 modified surviving paths are carried by the port (1 test modules held: fail on source branch too) |
| `fix/studio-per-scene-npc-terrain-20261030` | `3f737ce029` | 2026-10-30 | ported in PR #5767 | all 70 new / 0 modified surviving paths are carried by the port (17 test modules held: fail on source branch too) |
| `fix/studio-private-db-creation-20261030` | `6fefda0411` | 2026-10-30 | ported in PR #5767 | all 29 new / 0 modified surviving paths are carried by the port |
| `fix/studio-rejected-evidence-fence-20261030` | `466343496b` | 2026-10-30 | ported in PR #5767 | all 31 new / 0 modified surviving paths are carried by the port (1 test modules held: fail on source branch too) |
| `fix/studio-replay-before-mutate-20261030` | `9658354ada` | 2026-10-30 | ported in PR #5767 | all 42 new / 0 modified surviving paths are carried by the port (1 test modules held: fail on source branch too) |
| `fix/studio-single-fd-integrity-20261030` | `ef421b31d9` | 2026-10-30 | ported in PR #5767 | all 40 new / 0 modified surviving paths are carried by the port (1 test modules held: fail on source branch too) |
| `fix/studio-spectator-source-authority-20261020` | `5abeca35d3` | 2026-10-20 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/studio-story-content-hash-csp-20261030` | `f6da5c2ce0` | 2026-10-30 | ported in PR #5767 | all 68 new / 0 modified surviving paths are carried by the port (15 test modules held: fail on source branch too) |
| `fix/studio-v3-exact-runtime-resumption-20261030` | `fb4c8e40fe` | 2026-10-30 | ported in PR #5767 | all 58 new / 0 modified surviving paths are carried by the port (9 test modules held: fail on source branch too) |
| `fix/studio-validate-physics-before-hazard-damage-20261030` | `f2bcbe4a0d` | 2026-10-30 | ported in PR #5767 | all 68 new / 0 modified surviving paths are carried by the port (15 test modules held: fail on source branch too) |
| `fix/studio-walkable-content-hash-csp-20261030` | `4a9a416794` | 2026-10-30 | ported in PR #5767 | all 69 new / 0 modified surviving paths are carried by the port (16 test modules held: fail on source branch too) |
| `fix/studio-wave1-asset-job-kind-20261030` | `60786f5268` | 2026-10-30 | ported in PR #5767 | all 43 new / 0 modified surviving paths are carried by the port (1 test modules held: fail on source branch too) |
| `fix/studio-wave1-vector-art-palette-20261030` | `567cf56b25` | 2026-10-30 | ported in PR #5767 | all 42 new / 0 modified surviving paths are carried by the port (1 test modules held: fail on source branch too) |
| `fix/supervisor-bounded-fallback-20261025` | `cc4be4bdc1` | 2026-10-25 | fully on main | every changed blob already on main |
| `fix/swarm-async-supervisor-admission-20261105` | `07f1be8047` | 2026-11-09 | unique content pending port | 3 new files, 2 modified files survive a 3-way merge; e.g. backend/tests/test_swarm_async_supervisor_admission.py, backend/tests/test_swarm_build_source_admission.py, backend/tests/test_swarm_scheduler_receipt_truth.py |
| `fix/swarm-build-source-admission-20261105` | `5ccc9ca30b` | 2026-11-09 | unique content pending port | 3 new files, 2 modified files survive a 3-way merge; e.g. backend/tests/test_swarm_async_supervisor_admission.py, backend/tests/test_swarm_build_source_admission.py, backend/tests/test_swarm_scheduler_receipt_truth.py |
| `fix/swarm-directory-literal-provider-20261026` | `7f2deb1862` | 2026-10-26 | fully on main | every changed blob already on main |
| `fix/swarm-discourse-core-admission-20261105` | `ab36fbb28a` | 2026-11-09 | fully on main | every changed blob already on main |
| `fix/swarm-graph-tenant-custody-20261105` | `a63390ba1c` | 2026-11-09 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/swarm-planner-explicit-budget-contracts-20261105` | `2059afc29d` | 2026-11-09 | unique content pending port | 1 new files, 1 modified files survive a 3-way merge; e.g. backend/tests/test_swarm_scheduler_receipt_truth.py |
| `fix/swarm-scheduler-durable-receipts-20261105` | `0b31194dc9` | 2026-11-09 | unique content pending port | 2 new files, 2 modified files survive a 3-way merge; e.g. backend/tests/test_swarm_build_source_admission.py, backend/tests/test_swarm_scheduler_receipt_truth.py |
| `fix/swarm-seed-finite-admission-20261105` | `47fb9f2f89` | 2026-11-09 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/torch-checkpoint-weights-only-20261025` | `5305e2da9e` | 2026-10-25 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/traffic-dispatch-fast-regression-20261024` | `9d2a827ad9` | 2026-10-24 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/traffic-manager-operator-hold-20261026` | `5c5713c080` | 2026-10-26 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/traffic-policy-integer-caps-20261026` | `58cc073caf` | 2026-10-26 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `fix/trusted-studio-native-ci-convergence-20261108` | `5bb7349830` | 2026-11-08 | unique content pending port | 14 new files, 4 modified files survive a 3-way merge; e.g. skeleton/testing/test_installer_contract_failure_receipts.py, skeleton/testing/test_installer_diagnostic_recovery.py, skeleton/testing/test_installer_setup_probe_custody.py |
| `fix/unit-driving-workload-contract-20261025` | `c0735d63af` | 2026-10-25 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `fix/unit-repair-flag-explicit-json-20261029` | `a878097d79` | 2026-10-29 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `fix/unit-runtime-package-parity-20261026` | `6a73e4b973` | 2026-10-26 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `fix/unstable-branches-status-20261105` | `084addd116` | 2026-11-05 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. docs/ci/UNSTABLE_BRANCHES_2026-11-05.md |
| `fix/walt-realtime-authz-20261017` | `feccc30674` | 2026-10-18 | nothing unique | superseded: its 5 remaining edits conflict with newer main versions |
| `fix/walt-realtime-hardening-20261024` | `ed9f416a9c` | 2026-10-28 | unique content pending port | 0 new files, 230 modified files survive a 3-way merge; 1 paths already carried by port PRs |
| `fix/walt-realtime-sdk-errors-20261017` | `484230e466` | 2026-10-18 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `fix/watchdog-first-tick-503-20261025` | `ea655e25e8` | 2026-10-25 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `fix/wire-omnifabric-materialise-20261017` | `92378d9ec5` | 2026-10-17 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `grok/autonomous-game-studio-emulator-2026-10-29` | `b37de8e1e1` | 2026-10-29 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `grok/gap-security-assets-20261022` | `157bb8ae66` | 2026-10-22 | unique content pending port | 48 new files, 0 modified files survive a 3-way merge; e.g. skeleton/ai/runtime/weight_candidate_loop.py, skeleton/api/gap_routes.py, skeleton/app/GAP_COMMITS.md |
| `grok/sota-stack-max-2026-10-29` | `55f15f4547` | 2026-10-29 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. skeleton/cortex/sota_stack_maximiser.py |
| `grokbot/GB-deathmarch-collection-fixes` | `2f72ff92dc` | 2026-11-20 | unique content pending port | 0 new files, 7 modified files survive a 3-way merge |
| `grokbot/GB-repair-pickle-multimodal-secret` | `0aa5c06472` | 2026-11-19 | unique content pending port | 196 new files, 1438 modified files survive a 3-way merge; 9 paths already carried by port PRs; e.g. .github/workflows/ai-p0-current-main-validation.yml, .github/workflows/ai-product-completion.yml, .github/workflows/app-assembly.yml |
| `grokbot/GB-security-path-hardening-20261022` | `62eecaab36` | 2026-10-22 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `integrate/jeeves-native-laptop-operational-stack-20261104-r34` | `a0aa1354f8` | 2026-11-05 | nothing unique | superseded: its 145 remaining edits conflict with newer main versions |
| `integration/galaxy-158-genre-controls-script-runtime-20261113-r02` | `e1701b8cf3` | 2026-11-14 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `integration/galaxy-creator-custody-quality-20261113-r03` | `29e5235251` | 2026-11-14 | nothing unique | superseded: its 12 remaining edits conflict with newer main versions |
| `integration/galaxy-forge-roundtrip-draft-custody-20261113-r06` | `bfb0dd58bd` | 2026-11-14 | unique content pending port | 0 new files, 8 modified files survive a 3-way merge |
| `integration/gameforge-conductor-b039-20261113` | `4b9ff7e53d` | 2026-11-14 | unique content pending port | 0 new files, 2 modified files survive a 3-way merge |
| `integration/gameforge-source-archive-custody-20261113-r05` | `92ebf14b5b` | 2026-11-14 | nothing unique | superseded: its 9 remaining edits conflict with newer main versions |
| `integration/jeeves-interactive-game-runtime-20261113-r01` | `f8d9bbe2ef` | 2026-11-14 | unique content pending port | 0 new files, 3 modified files survive a 3-way merge; 2 paths already carried by port PRs |
| `integration/jeeves-user-prototype-20261112` | `62b54e1983` | 2026-11-14 | unique content pending port | 0 new files, 6 modified files survive a 3-way merge |
| `integration/native-eight-scene-playtest-20261113-r04` | `0fddd019f7` | 2026-11-14 | unique content pending port | 0 new files, 2 modified files survive a 3-way merge |
| `integration/studio-forge-project-return-custody-20261113-r07` | `da69806858` | 2026-11-14 | unique content pending port | 0 new files, 2 modified files survive a 3-way merge |
| `integration/studio-forge-source-bound-return-20261114-r07` | `fb9692f379` | 2026-11-14 | unique content pending port | 0 new files, 2 modified files survive a 3-way merge |
| `integration/verticals-end-user-20261119` | `03aa26930e` | 2026-11-20 | unique content pending port | 28 new files, 37 modified files survive a 3-way merge; 3 paths already carried by port PRs; open PR #5709 (mergeable) -> main; e.g. backend/core/dragon_native_projects.py, backend/tests/test_dragon_creator_projects.py, backend/tests/test_gameforge_durable_source.py |
| `is/agent-edge-fold` | `c658e22d0a` | 2026-10-17 | nothing unique | superseded: its 6 remaining edits conflict with newer main versions |
| `is/app-foundation-persistence` | `c71ad46704` | 2026-10-17 | nothing unique | superseded: its 17 remaining edits conflict with newer main versions |
| `is/cortex-guard-fail-closed` | `418b580804` | 2026-10-24 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `is/job-event-ownership` | `57ef14fff5` | 2026-10-24 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `is/persistence-freeze` | `0754b20adf` | 2026-10-17 | nothing unique | superseded: its 20 remaining edits conflict with newer main versions |
| `is/seal-v2-domain-nonce` | `078a83de2a` | 2026-10-24 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `is/traceability-spine-resync` | `0ace61724f` | 2026-10-17 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `jenkins/restore-omnifabric-mount-20261024` | `10843e6050` | 2026-10-25 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `jenkins/td-negative-tests-20261024` | `56996a0677` | 2026-10-24 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `klint/4138-plan` | `a2d1bbef51` | 2026-10-24 | unique content pending port | 2 new files, 0 modified files survive a 3-way merge; e.g. artifacts/klint/4138-plan.md, artifacts/klint/status-20261024-1850.md |
| `laneA/fix-deepmerge-interrupted-rerun-test` | `9a4fd004cc` | 2026-11-22 | not analysed | merge-tree unavailable |
| `laneA/fix-godot-forge-custody-tests` | `e6b14a4366` | 2026-11-22 | not analysed | merge-tree unavailable |
| `laneA/fix-lazy-registry-loaders` | `86358f9ab1` | 2026-11-22 | not analysed | merge-tree unavailable |
| `laneA/fix-product-surface-digests` | `a6c6c7e8bc` | 2026-11-22 | not analysed | merge-tree unavailable |
| `laneA/fix-readiness-account-transport` | `3af6c761e1` | 2026-11-22 | not analysed | merge-tree unavailable |
| `laneA/fix-storage-scope-rollback-test` | `c33e5ab318` | 2026-11-22 | not analysed | merge-tree unavailable |
| `laneA/main-green-20261122` | `a517b51117` | 2026-11-22 | not analysed | merge-tree unavailable |
| `laneA/restore-native-scene-qualification` | `e10807f54b` | 2026-11-22 | not analysed | merge-tree unavailable |
| `mass-archive-1` | `a18a9ad21f` | 2026-11-14 | fully on main | every changed blob already on main |
| `mass-archive-10` | `cb712eca4a` | 2026-11-14 | fully on main | every changed blob already on main |
| `mass-archive-100` | `af6516741f` | 2026-11-19 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `mass-archive-101` | `cdca69c903` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-102` | `a3f7548624` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-103` | `a9e9967edd` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-104` | `971abcc1fa` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-105` | `f7ebd93141` | 2026-11-19 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `mass-archive-106` | `fa927ff447` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-107` | `33f381b89e` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-108` | `07e33b7c79` | 2026-11-19 | nothing unique | superseded: its 5 remaining edits conflict with newer main versions |
| `mass-archive-109` | `0cf049e9f1` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-11` | `f94e138d19` | 2026-11-14 | nothing unique | superseded: its 6 remaining edits conflict with newer main versions |
| `mass-archive-110` | `077b3dbdb0` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-111` | `554f2b41e8` | 2026-11-19 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `mass-archive-112` | `031cdafcb6` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-113` | `1c761b4027` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-114` | `5967378122` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-115` | `20ddb10864` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-116` | `d79a9800fa` | 2026-11-19 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `mass-archive-117` | `dcaa302be4` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-118` | `2d49fd02fa` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-119` | `f6fdfc4a04` | 2026-11-19 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `mass-archive-12` | `9cd1d7d5a9` | 2026-11-14 | fully on main | every changed blob already on main |
| `mass-archive-120` | `354152e829` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-121` | `94c3aa39bd` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-122` | `54a671fdc3` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-123` | `79ae141243` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-13` | `94ddbd0bf9` | 2026-11-14 | fully on main | every changed blob already on main |
| `mass-archive-14` | `3e1a4e37f8` | 2026-11-14 | fully on main | 0 commits ahead |
| `mass-archive-15` | `2585061236` | 2026-11-14 | fully on main | every changed blob already on main |
| `mass-archive-16` | `4dd6d542f6` | 2026-11-14 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `mass-archive-17` | `ca7b79e1b0` | 2026-11-14 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `mass-archive-18` | `512167deff` | 2026-11-14 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `mass-archive-19` | `db710b3d72` | 2026-11-14 | fully on main | every changed blob already on main |
| `mass-archive-2` | `25e37ffc5d` | 2026-11-14 | fully on main | every changed blob already on main |
| `mass-archive-20` | `eb7f53fefb` | 2026-11-14 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `mass-archive-21` | `b167987178` | 2026-11-14 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `mass-archive-22` | `1b8b4f921e` | 2026-11-15 | fully on main | every changed blob already on main |
| `mass-archive-23` | `f2e453ee70` | 2026-11-15 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `mass-archive-24` | `9f592ba17b` | 2026-11-15 | fully on main | every changed blob already on main |
| `mass-archive-25` | `ec4a32cc99` | 2026-11-15 | fully on main | every changed blob already on main |
| `mass-archive-26` | `1cf70a19a8` | 2026-11-15 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `mass-archive-27` | `cece671e06` | 2026-11-15 | fully on main | every changed blob already on main |
| `mass-archive-28` | `95736b6cfa` | 2026-11-15 | fully on main | every changed blob already on main |
| `mass-archive-29` | `b55c279d76` | 2026-11-15 | fully on main | every changed blob already on main |
| `mass-archive-3` | `4bc51dd8ca` | 2026-11-14 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `mass-archive-30` | `5eb53fdc80` | 2026-11-15 | fully on main | every changed blob already on main |
| `mass-archive-31` | `7c6ffc53b7` | 2026-11-16 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `mass-archive-32` | `5ea2706e1b` | 2026-11-16 | fully on main | every changed blob already on main |
| `mass-archive-33` | `37fae5cf56` | 2026-11-16 | fully on main | every changed blob already on main |
| `mass-archive-34` | `d43d52a97b` | 2026-11-16 | nothing unique | superseded: its 6 remaining edits conflict with newer main versions |
| `mass-archive-35` | `375c1c978a` | 2026-11-16 | fully on main | every changed blob already on main |
| `mass-archive-36` | `bcffa8d517` | 2026-11-16 | fully on main | every changed blob already on main |
| `mass-archive-37` | `24b70a4497` | 2026-11-16 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `mass-archive-38` | `e7c546475f` | 2026-11-16 | fully on main | every changed blob already on main |
| `mass-archive-39` | `1e67993b36` | 2026-11-16 | fully on main | every changed blob already on main |
| `mass-archive-4` | `a220dc1720` | 2026-11-14 | fully on main | every changed blob already on main |
| `mass-archive-40` | `d8a2f580fd` | 2026-11-16 | fully on main | every changed blob already on main |
| `mass-archive-41` | `22099a8ba9` | 2026-11-16 | fully on main | every changed blob already on main |
| `mass-archive-42` | `46491490ee` | 2026-11-16 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `mass-archive-43` | `3499821df4` | 2026-11-16 | fully on main | every changed blob already on main |
| `mass-archive-44` | `eae35685b5` | 2026-11-16 | fully on main | every changed blob already on main |
| `mass-archive-45` | `6e2f1af5c0` | 2026-11-16 | nothing unique | superseded: its 6 remaining edits conflict with newer main versions |
| `mass-archive-46` | `0ce2c8e486` | 2026-11-17 | fully on main | every changed blob already on main |
| `mass-archive-47` | `f935e181db` | 2026-11-17 | fully on main | every changed blob already on main |
| `mass-archive-48` | `1a1c6b0ba9` | 2026-11-17 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `mass-archive-49` | `0fbaa07be5` | 2026-11-17 | fully on main | every changed blob already on main |
| `mass-archive-5` | `8496bf3d24` | 2026-11-14 | fully on main | every changed blob already on main |
| `mass-archive-50` | `50b2d9ac0c` | 2026-11-17 | fully on main | every changed blob already on main |
| `mass-archive-51` | `7d4502109c` | 2026-11-17 | fully on main | every changed blob already on main |
| `mass-archive-52` | `10d3cb1fad` | 2026-11-17 | fully on main | every changed blob already on main |
| `mass-archive-53` | `cd67aac7ec` | 2026-11-17 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `mass-archive-54` | `8c75aa1617` | 2026-11-17 | fully on main | every changed blob already on main |
| `mass-archive-55` | `a640bc255f` | 2026-11-17 | fully on main | every changed blob already on main |
| `mass-archive-56` | `f4164fc414` | 2026-11-17 | nothing unique | superseded: its 6 remaining edits conflict with newer main versions |
| `mass-archive-57` | `098f591561` | 2026-11-17 | fully on main | every changed blob already on main |
| `mass-archive-58` | `9767e3c442` | 2026-11-17 | fully on main | every changed blob already on main |
| `mass-archive-59` | `4b9ade7be4` | 2026-11-17 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `mass-archive-6` | `60893db2ee` | 2026-11-14 | fully on main | every changed blob already on main |
| `mass-archive-60` | `cdb8549702` | 2026-11-17 | fully on main | every changed blob already on main |
| `mass-archive-61` | `06d8b28655` | 2026-11-18 | fully on main | every changed blob already on main |
| `mass-archive-62` | `f42f59dcd8` | 2026-11-18 | fully on main | every changed blob already on main |
| `mass-archive-63` | `c8dc35cdb9` | 2026-11-18 | fully on main | every changed blob already on main |
| `mass-archive-64` | `45ca9334d0` | 2026-11-18 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `mass-archive-65` | `bc7ab4c04a` | 2026-11-18 | fully on main | every changed blob already on main |
| `mass-archive-66` | `caa1f2763c` | 2026-11-18 | fully on main | every changed blob already on main |
| `mass-archive-67` | `ce1aa590ec` | 2026-11-18 | nothing unique | superseded: its 6 remaining edits conflict with newer main versions |
| `mass-archive-68` | `73cda2edcc` | 2026-11-18 | fully on main | every changed blob already on main |
| `mass-archive-69` | `7c29984301` | 2026-11-18 | fully on main | every changed blob already on main |
| `mass-archive-7` | `b88ab48fc0` | 2026-11-14 | fully on main | every changed blob already on main |
| `mass-archive-70` | `acf20579c6` | 2026-11-18 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `mass-archive-71` | `e34c0b35c7` | 2026-11-18 | fully on main | every changed blob already on main |
| `mass-archive-72` | `a7b2b09a0e` | 2026-11-18 | fully on main | every changed blob already on main |
| `mass-archive-73` | `70faee6d19` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-74` | `719054fe04` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-75` | `3c0ce4784e` | 2026-11-19 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `mass-archive-76` | `0f3e314863` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-77` | `1c261a9abc` | 2026-11-19 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `mass-archive-78` | `945e16f291` | 2026-11-19 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `mass-archive-79` | `e8c144901b` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-8` | `38b78a3879` | 2026-11-14 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `mass-archive-80` | `d88196f443` | 2026-11-19 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `mass-archive-81` | `6185b21847` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-82` | `c55aec7aba` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-83` | `b95cf6b6e6` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-84` | `93cff2ebd5` | 2026-11-19 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `mass-archive-85` | `9e263896f2` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-86` | `dbc140b40e` | 2026-11-19 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `mass-archive-87` | `6df8f9385d` | 2026-11-19 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `mass-archive-88` | `fc4ac6fd8e` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-89` | `0005b879e9` | 2026-11-19 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `mass-archive-9` | `b964b2c7f0` | 2026-11-14 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `mass-archive-90` | `45ed43f02a` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-91` | `865bd794c2` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-92` | `7bfb25fdb6` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-93` | `db9ee7074e` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-94` | `7807b04506` | 2026-11-19 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `mass-archive-95` | `f07fa355df` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-96` | `b65f261a24` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-97` | `c4b01af8b6` | 2026-11-19 | nothing unique | superseded: its 5 remaining edits conflict with newer main versions |
| `mass-archive-98` | `3436089bbd` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-archive-99` | `7b04cb3171` | 2026-11-19 | fully on main | every changed blob already on main |
| `mass-recovery` | `ce33e4fdaa` | 2026-11-14 | unique content pending port | 0 new files, 2 modified files survive a 3-way merge |
| `mass-recovery-10` | `5f0af01e04` | 2026-11-14 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge; 1 paths already carried by port PRs |
| `mass-recovery-11` | `cfd83c0d80` | 2026-11-14 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `mass-recovery-12` | `e02c074e3d` | 2026-11-14 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `mass-recovery-13` | `a6fbb53d6b` | 2026-11-14 | fully on main | every changed blob already on main |
| `mass-recovery-14` | `c469c4827c` | 2026-11-14 | fully on main | every changed blob already on main |
| `mass-recovery-15` | `2fa6663385` | 2026-11-14 | unique content pending port | 0 new files, 2 modified files survive a 3-way merge |
| `mass-recovery-16` | `3268b86e77` | 2026-11-14 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `mass-recovery-2` | `11fa522a97` | 2026-11-14 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `mass-recovery-3` | `276a7df5af` | 2026-11-14 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `mass-recovery-4` | `39c68fa38f` | 2026-11-14 | ported in PR #5771 | all 0 new / 1 modified surviving paths are carried by the port |
| `mass-recovery-5` | `fe345bf517` | 2026-11-14 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `mass-recovery-6` | `8b5ee7423f` | 2026-11-14 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `mass-recovery-7` | `8e752319ee` | 2026-11-14 | unique content pending port | 0 new files, 2 modified files survive a 3-way merge |
| `mass-recovery-8` | `da38accb1a` | 2026-11-14 | unique content pending port | 0 new files, 2 modified files survive a 3-way merge; 1 paths already carried by port PRs |
| `mass-recovery-9` | `eef35a693d` | 2026-11-14 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `murash/economy-inventory-currency-sinks` | `8fc9325989` | 2026-10-25 | fully on main | every changed blob already on main |
| `perf/bounded-parallel-repository-inventory-20261023` | `e3a1c23f32` | 2026-10-23 | fully on main | every changed blob already on main |
| `prototype/dragon-atelier-crawler-renderer-20261117` | `d4595110f1` | 2026-11-17 | unique content pending port | 7 new files, 1 modified files survive a 3-way merge; open PR #5506 (mergeable) -> prototype/dragon-atelier-flight-runtime-20261117; e.g. frontend/scripts/test-dragon-atelier-runtime.cjs, frontend/src/features/Jeeves/companion/atelier/AtelierPrototype.tsx, frontend/src/features/Jeeves/companion/atelier/AtelierPrototype.web.tsx |
| `prototype/dragon-atelier-flight-runtime-20261117` | `d5f5e9a9f1` | 2026-11-17 | unique content pending port | 3 new files, 0 modified files survive a 3-way merge; open PR #5505 (mergeable) -> prototype/dragon-atelier-fold-custody-20261117; e.g. frontend/scripts/test-dragon-atelier-runtime.cjs, frontend/src/features/Jeeves/companion/atelier/atelierAsset.ts, frontend/src/features/Jeeves/companion/atelier/atelierDirector.ts |
| `prototype/dragon-atelier-fold-custody-20261117` | `9391a4bea2` | 2026-11-17 | fully on main | every changed blob already on main |
| `prototype/dragon-atelier-pilot-qualification-20261117` | `22c22d22ad` | 2026-11-17 | unique content pending port | 10 new files, 2 modified files survive a 3-way merge; open PR #5507 (mergeable) -> prototype/dragon-atelier-crawler-renderer-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, docs/DRAGON_ATELIER_PROTOTYPE_ACCEPTANCE.md, frontend/scripts/test-dragon-atelier-integration.cjs |
| `prototype/dragon-atelier-visual-inspection-20261117` | `a63afd2e63` | 2026-11-17 | unique content pending port | 11 new files, 2 modified files survive a 3-way merge; open PR #5508 (mergeable) -> prototype/dragon-atelier-pilot-qualification-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, docs/DRAGON_ATELIER_INSPECTION_LAB.md, docs/DRAGON_ATELIER_PROTOTYPE_ACCEPTANCE.md |
| `qa/app-foundation-e2e` | `7e328e8a59` | 2026-10-17 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `qa/cherry-image-contract-test-20261114` | `424a4725e8` | 2026-11-14 | fully on main | every changed blob already on main |
| `qa/cherry-jeeves-capsule-launchers-20261114` | `f959b470ce` | 2026-11-14 | fully on main | every changed blob already on main |
| `qa/cherry-laptop-recovery-guard-tests-20261114` | `d88fcbb0e2` | 2026-11-15 | fully on main | every changed blob already on main |
| `qa/cherry-loopback-ports-test-20261114` | `d8b422b617` | 2026-11-14 | fully on main | every changed blob already on main |
| `qa/cherry-path-hardening-20261114` | `7c3c7830a4` | 2026-11-15 | fully on main | every changed blob already on main |
| `qa/cherry-postmerge-replay-v2-tests-20261114` | `9d256087c2` | 2026-11-15 | fully on main | every changed blob already on main |
| `qa/cherry-replay-determinism-tests-20261114` | `d841797765` | 2026-11-15 | fully on main | every changed blob already on main |
| `qa/cherry-telemetry-121-20261114` | `e90b9d9b3e` | 2026-11-15 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `qa/full-regression-gate-20261114` | `26bc89e47b` | 2026-11-14 | fully on main | every changed blob already on main |
| `qualification/game-save-postmerge-custody-20261110-r01` | `1e82ecf3a9` | 2026-11-10 | nothing unique | superseded: its 22 remaining edits conflict with newer main versions |
| `qualification/source-exact-27path-convergence-20261110` | `1ad1fc3e7a` | 2026-11-11 | nothing unique | superseded: its 22 remaining edits conflict with newer main versions |
| `rebase/archive/pre-rebase-frontier-chunk-telemetry-20261113-fbe19010` | `d4230a476c` | 2026-11-14 | fully on main | every changed blob already on main |
| `rebase/archive/pre-rebase-gf-b040-s4s5-20261113-c6a5a6c7` | `cedd97e7c2` | 2026-11-14 | fully on main | every changed blob already on main |
| `rebase/archive/pre-rebase-mb-gfa-20261113-ce1bf3c1` | `33782657a3` | 2026-11-14 | fully on main | every changed blob already on main |
| `rebase/reconcile/flgb-iterative-scene-transform-20261108-r01` | `933c9f647a` | 2026-11-14 | fully on main | every changed blob already on main |
| `rebase/reconcile/local-ai-native-readiness-failclosed-20261108-r01` | `d9f36dacf5` | 2026-11-15 | fully on main | every changed blob already on main |
| `reconcile/421-source-bound-volume-dossiers-20261109` | `b3b4c86da6` | 2026-11-09 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `reconcile/ai-ci-20-gate-current-owner-refresh-20261109` | `b5866bf875` | 2026-11-09 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `reconcile/ai-historical-native-recovery-20261114-b03` | `5045484c97` | 2026-11-14 | fully on main | every changed blob already on main |
| `reconcile/ai-tree-parity-pin-refresh-current-main-20261109` | `28de4b0e64` | 2026-11-09 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `reconcile/ai-tree-pins-world-mirror-do-not-merge-20261109-r01` | `efcb600b58` | 2026-11-10 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `reconcile/api-v1-58-exact-source-mirrors-20261109` | `523d650553` | 2026-11-09 | fully on main | every changed blob already on main |
| `reconcile/app-foundation-divergence-20261114-b01` | `5906e693b3` | 2026-11-14 | fully on main | every changed blob already on main |
| `reconcile/audited-runtime-parity-20261114-r01` | `4cda032b09` | 2026-11-16 | unique content pending port | 137 new files, 84 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5405 (conflicting) -> main; e.g. .gitleaksignore, backend/core/core_v1/envelope.py, backend/core/core_v1/keys.py |
| `reconcile/backend-e2e-python314-pin-20261108-r1` | `e2d28b6231` | 2026-11-11 | fully on main | every changed blob already on main |
| `reconcile/backup-pr-4551-e559e56963b68703939848b2da300003d4680b51` | `e559e56963` | 2026-11-05 | unique content pending port | 0 new files, 2 modified files survive a 3-way merge |
| `reconcile/backup-pr-4636-49b976c4415d770892f80d2fe5a003cf9356cd41` | `49b976c441` | 2026-11-02 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `reconcile/backup-pr-4638-35e2f7bcdaf5e10b237743207d66aa4040f8ce65` | `35e2f7bcda` | 2026-11-02 | nothing unique | superseded: its 8 remaining edits conflict with newer main versions |
| `reconcile/backup-pr-4641-88b357cc1ab55d53cb76c083145adbf4fd30ace7` | `88b357cc1a` | 2026-11-02 | nothing unique | superseded: its 23 remaining edits conflict with newer main versions |
| `reconcile/backup-pr-4644-2180a9ec887911b724d8372d6390e14ba5c222f5` | `2180a9ec88` | 2026-11-02 | nothing unique | superseded: its 7 remaining edits conflict with newer main versions |
| `reconcile/backup-pr-4652-d53777321fa4bef096c71f94df4b18e0d9ed2aa1` | `d53777321f` | 2026-11-02 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `reconcile/backup-pr-4654-6626c3c9346779f467ba350d358f99f2d8f38c9c` | `6626c3c934` | 2026-11-03 | nothing unique | superseded: its 7 remaining edits conflict with newer main versions |
| `reconcile/backup-pr-4659-d24cebe07d64c64b810562ec9170bf0189346a62` | `d24cebe07d` | 2026-11-03 | nothing unique | superseded: its 11 remaining edits conflict with newer main versions |
| `reconcile/backup-pr-4665-17e752a2251a40fc1ddc392f01559c00a4b576ff` | `17e752a225` | 2026-11-03 | nothing unique | superseded: its 9 remaining edits conflict with newer main versions |
| `reconcile/backup-pr-4666-ab66760cc7baea7c59bed6b0031c305681bca5a5` | `ab66760cc7` | 2026-11-03 | nothing unique | superseded: its 11 remaining edits conflict with newer main versions |
| `reconcile/backup-pr-4671-5568ddc4297b06078128a81f3e66daff49db0c24` | `5568ddc429` | 2026-11-03 | nothing unique | superseded: its 11 remaining edits conflict with newer main versions |
| `reconcile/backup-pr-4685-2551aa149d5908a661b3a3a9ca2307aa5dfcd217` | `2551aa149d` | 2026-11-03 | unique content pending port | 9 new files, 0 modified files survive a 3-way merge; e.g. skeleton/testing/test_ai_reliability_flow_bundle.py, skeleton/testing/test_ai_reliability_flow_deadline.py, skeleton/testing/test_ai_reliability_flow_event_chain.py |
| `reconcile/canonical-forge-jeeves-1644-mirror-parity-20261109` | `223d4a4509` | 2026-11-10 | nothing unique | superseded: its 11 remaining edits conflict with newer main versions |
| `reconcile/ci-first-blockers-do-not-merge-20261109-r01` | `41dbcaf939` | 2026-11-10 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `reconcile/ci-hold-galaxy-native-20261111-r01` | `40af9195b1` | 2026-11-11 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `reconcile/ci-import-security-main-20261111-r01` | `ebf9639f80` | 2026-11-11 | nothing unique | superseded: its 19 remaining edits conflict with newer main versions |
| `reconcile/ci-literal-and-mainline-20261111-r01` | `d0a447d5e0` | 2026-11-11 | nothing unique | superseded: its 19 remaining edits conflict with newer main versions |
| `reconcile/codex-content-scrutiny-20261024` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `reconcile/codex-promotion-regression-20261024` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `reconcile/combined-game-runtime-custody-20261114-r03` | `8b1e7d5130` | 2026-11-16 | fully on main | every changed blob already on main |
| `reconcile/consumer-compose-loopback-tests-20261108-r01` | `e7ee13e2ec` | 2026-11-08 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `reconcile/consumer-compose-private-published-regression-20261108-r02` | `3ee9853206` | 2026-11-08 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `reconcile/consumer-probes-cors-20261109-r03` | `e47e94c090` | 2026-11-10 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `reconcile/creator-quest-godot-convergence-20261113-r01` | `baf8ea994a` | 2026-11-14 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `reconcile/discourse-durable-jobs-surface-20261111-r01` | `947fba714f` | 2026-11-11 | nothing unique | superseded: its 9 remaining edits conflict with newer main versions |
| `reconcile/draft-promotion-source-convergence-20261108-r03` | `55e6a1052f` | 2026-11-08 | unique content pending port | 30 new files, 6 modified files survive a 3-way merge; 68 paths already carried by port PRs; e.g. .github/workflows/jeeves-atomic-review-regression.yml, .github/workflows/reconciliation-exact-head-policy.yml, .github/workflows/reconciliation-game-source-qualification.yml |
| `reconcile/draft19-gguf-path-custody-20261108` | `295185f09f` | 2026-11-11 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `reconcile/draft19-studio-archive-inspection-20261108-r01` | `6b5fc279e4` | 2026-11-11 | unique content pending port | 30 new files, 6 modified files survive a 3-way merge; 68 paths already carried by port PRs; e.g. .github/workflows/jeeves-atomic-review-regression.yml, .github/workflows/reconciliation-exact-head-policy.yml, .github/workflows/reconciliation-game-source-qualification.yml |
| `reconcile/dragon-atlas-ui-backend-on-core-20261109` | `aaf2db59cb` | 2026-11-09 | nothing unique | superseded: its 8 remaining edits conflict with newer main versions |
| `reconcile/dragon-research-core-317-20261109` | `6fa9262ed0` | 2026-11-09 | nothing unique | superseded: its 8 remaining edits conflict with newer main versions |
| `reconcile/emerald-peak-unified-20261117` | `5f2e92271f` | 2026-11-17 | unique content pending port | 30 new files, 6 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5510 (mergeable) -> fix/emerald-shared-source-gates-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, artifacts/emerald/.gitignore, docs/DRAGON_ATELIER_INSPECTION_LAB.md |
| `reconcile/feature-frontier-native-runtime-20261114-b01` | `aa008befe1` | 2026-11-14 | fully on main | every changed blob already on main |
| `reconcile/first-install-critical-convergence-20261116-r01` | `7ffe6da8f2` | 2026-11-16 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `reconcile/first-install-critical-path-20261116-r01` | `6edf60f234` | 2026-11-16 | unique content pending port | 83 new files, 119 modified files survive a 3-way merge; 3 paths already carried by port PRs; open PR #5479 (conflicting) -> main; e.g. .github/workflows/exact-gguf-physical-cpu-qualification.yml, .github/workflows/independent-reviewer-qualification.yml, .github/workflows/isolated-chroma-persistence-qualification.yml |
| `reconcile/first-install-loopback-assembly-current-parent-20261108-r01` | `1966dc7452` | 2026-11-10 | nothing unique | superseded: its 67 remaining edits conflict with newer main versions |
| `reconcile/first-install-mass-batch-20261108-b04` | `c8fbcce770` | 2026-11-14 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `reconcile/first-install-merge-readiness-test-custody-20261108-r01` | `cac0c49220` | 2026-11-10 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `reconcile/first-install-security-convergence-20261108-b05` | `d2716ad136` | 2026-11-08 | unique content pending port | 10 new files, 53 modified files survive a 3-way merge; 1 paths already carried by port PRs; e.g. skeleton/testing/test_game_project_cli_custody.py, skeleton/testing/test_game_project_cli_input_budget.py, skeleton/testing/test_godot_export_cli_custody.py |
| `reconcile/flgb-iterative-scene-transform-20261108-r01` | `a2f42385b8` | 2026-11-08 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. tests/test_flgb_transform_hierarchy_depth.py |
| `reconcile/forge-ai-builder-and-visual-editor-20261109` | `0b6b70ea37` | 2026-11-09 | nothing unique | superseded: its 5 remaining edits conflict with newer main versions |
| `reconcile/forge-continuity-main-20261023` | `ab54ea8a2a` | 2026-10-23 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `reconcile/full-repo-audit-manual-bounded-20261108-r01` | `6ab127c111` | 2026-11-08 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. tests/test_full_repo_audit_bounded_evidence.py |
| `reconcile/game-frontier-archived-runtime-heavy-20261113-r01` | `578aeb324b` | 2026-11-14 | fully on main | every changed blob already on main |
| `reconcile/game-frontier-postmerge-native-runtime-20261113` | `cfd1764b91` | 2026-11-14 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `reconcile/game-route-scene-depth-20261109-r04` | `382329e123` | 2026-11-09 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `reconcile/game-save-e2e-current-parent-20261111-r01` | `c1a3416882` | 2026-11-11 | nothing unique | superseded: its 25 remaining edits conflict with newer main versions |
| `reconcile/gamebuilder-e2e-test-custody-20261113-r1` | `8b7a28be7e` | 2026-11-14 | fully on main | every changed blob already on main |
| `reconcile/gguf-artifact-custody-20261109-r09` | `1e06e7b438` | 2026-11-09 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `reconcile/gguf-artifact-full-custody-20261109-r09` | `660718f31a` | 2026-11-09 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `reconcile/grid-save-slot-custody-20261109-r07` | `39dc01eb7c` | 2026-11-10 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `reconcile/health-response-metadata` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `reconcile/held-first-install-custody-20261109-r01` | `2bbfc5a35e` | 2026-11-09 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `reconcile/held-source-mainline-36paths-20261111-r01` | `795fbeffd9` | 2026-11-11 | nothing unique | superseded: its 13 remaining edits conflict with newer main versions |
| `reconcile/historical-hyper-draft-source-custody-20261114-r01` | `b77fe0dd52` | 2026-11-14 | fully on main | every changed blob already on main |
| `reconcile/historical-offline-runtime-recovery-20261114-b03` | `70247b8823` | 2026-11-14 | nothing unique | superseded: its 19 remaining edits conflict with newer main versions |
| `reconcile/historical-prototype-lab-20261114-r01` | `99eb66f287` | 2026-11-14 | fully on main | every changed blob already on main |
| `reconcile/historical-studio-qa-custody-20261114-r01` | `ac29982010` | 2026-11-19 | fully on main | every changed blob already on main |
| `reconcile/jeeves-browser-save-20261109-r05` | `7de83fe6d4` | 2026-11-10 | unique content pending port | 1 new files, 4 modified files survive a 3-way merge; e.g. skeleton/testing/test_jeeves_browser_save.py |
| `reconcile/jeeves-lease-media-custody-20261114-r01` | `f80d62aecb` | 2026-11-15 | fully on main | every changed blob already on main |
| `reconcile/jeeves-offline-builder-missing-20261114-r01` | `8362136f0e` | 2026-11-15 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `reconcile/jeeves-offline-builder-recovery-20261114-r01` | `5117c9726a` | 2026-11-15 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `reconcile/jeeves-offline-builder-three-way-20261114-r01` | `b8c3895c07` | 2026-11-16 | unique content pending port | 0 new files, 3 modified files survive a 3-way merge; open PR #5373 (conflicting) -> main |
| `reconcile/jeeves-world-custody-mirror-20261109-r02` | `12189a0a77` | 2026-11-10 | unique content pending port | 1 new files, 4 modified files survive a 3-way merge; e.g. skeleton/testing/test_jeeves_browser_save.py |
| `reconcile/jeeves-world-player-save-keyboard-20261108-r01` | `8c1a82abe0` | 2026-11-08 | unique content pending port | 2 new files, 0 modified files survive a 3-way merge; e.g. skeleton/testing/test_jeeves_browser_save_contract.py, skeleton/testing/test_jeeves_world_player_save_keyboard_integration.py |
| `reconcile/jeeves-world-player-source-custody-20261108-r01` | `40e35d2248` | 2026-11-08 | unique content pending port | 2 new files, 0 modified files survive a 3-way merge; e.g. skeleton/testing/test_jeeves_browser_save_contract.py, skeleton/testing/test_jeeves_world_player_save_keyboard_integration.py |
| `reconcile/legacy-ai-truth-and-gguf-custody-20261109-r08` | `25325b481b` | 2026-11-10 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `reconcile/legacy-local-ai-truthful-readiness-20261109-r08` | `201cd0eebe` | 2026-11-09 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `reconcile/local-ai-native-readiness-failclosed-20261108-r01` | `b6e2766632` | 2026-11-08 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `reconcile/local-ai-truth-loader-runtime-doctor-20261108-r01` | `494cd14ce8` | 2026-11-08 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `reconcile/main-ci-security-literal-dispatch-20261111-r01` | `917b2fd23d` | 2026-11-11 | nothing unique | superseded: its 7 remaining edits conflict with newer main versions |
| `reconcile/mainline-guarded-e2e-replay-20261111-r01` | `98304e7f41` | 2026-11-11 | nothing unique | superseded: its 5 remaining edits conflict with newer main versions |
| `reconcile/mass-game-telemetry-qa-20261114-r01` | `a0d2a75607` | 2026-11-15 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `reconcile/mirror-first-install-shared-gates-20261108-r01` | `36acfc8b91` | 2026-11-08 | nothing unique | superseded: its 17 remaining edits conflict with newer main versions |
| `reconcile/murash-industry-crafting-20261114-r01` | `5027122c50` | 2026-11-15 | fully on main | every changed blob already on main |
| `reconcile/native-ai-recovery-20261114-b03` | `53a1664ba8` | 2026-11-14 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `reconcile/native-profile-strict-evidence-20261108-r01` | `6c21d5492e` | 2026-11-08 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `reconcile/native-report-custody-escape-convergence-20261111` | `07b753e063` | 2026-11-11 | nothing unique | superseded: its 23 remaining edits conflict with newer main versions |
| `reconcile/native-report-escaped-json-bound-20261111` | `1cf5abd528` | 2026-11-11 | nothing unique | superseded: its 22 remaining edits conflict with newer main versions |
| `reconcile/orphan-offline-runtime-admission-20261116` | `5b988cae3c` | 2026-11-16 | unique content pending port | 126 new files, 42 modified files survive a 3-way merge; 2 paths already carried by port PRs; open PR #5487 (conflicting) -> main; e.g. docs/ai/MEASURED_PROTECTED_JEEVES_DEPLOYMENT.md, docs/ai/OFFLINE_RUNTIME_EXECUTION_CUSTODY.md, docs/ai/ORPHAN_SOURCE_GRAPH.md |
| `reconcile/orphan-quest-runtime-entrypoint-20261116` | `167b761440` | 2026-11-16 | fully on main | every changed blob already on main |
| `reconcile/p0-integrated-mass-custody-20261108-r01` | `4e9bb17b93` | 2026-11-11 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `reconcile/p0-mass-dragon-studio-security-20261108-r02` | `888584fca6` | 2026-11-11 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `reconcile/p0-mass-dragon-volumes-20261108-r01` | `a96531377f` | 2026-11-08 | unique content pending port | 13 new files, 5 modified files survive a 3-way merge; 68 paths already carried by port PRs; e.g. skeleton/testing/test_installer_contract_failure_receipts.py, skeleton/testing/test_installer_diagnostic_recovery.py, skeleton/testing/test_installer_setup_probe_custody.py |
| `reconcile/perf-clock-domain-failure-replay-20261111-r01` | `9d25ee5d52` | 2026-11-11 | nothing unique | superseded: its 22 remaining edits conflict with newer main versions |
| `reconcile/physics-export-mirror-main-20261110-r01` | `a45492643b` | 2026-11-10 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `reconcile/pr5107-policy-clean-20261109-0329` | `da46e8ebee` | 2026-11-09 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `reconcile/pr5122-loopback-main-20261109-0329` | `d34337f594` | 2026-11-09 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `reconcile/quarantine-ai-builder-procgen-20261108-r1` | `496633924c` | 2026-11-09 | nothing unique | superseded: its 7 remaining edits conflict with newer main versions |
| `reconcile/quarantine-api-v1-edge-20261108-r1` | `719acba050` | 2026-11-09 | unique content pending port | 1 new files, 2 modified files survive a 3-way merge; e.g. tests/test_ci_workflow_admission_budgets_20261108.py |
| `reconcile/quarantine-creator-visual-editor-20261108-r1` | `a1b4bc3a9a` | 2026-11-09 | nothing unique | superseded: its 16 remaining edits conflict with newer main versions |
| `reconcile/quarantine-ecs-agent-ai-20261108-r1` | `5f89f589ba` | 2026-11-09 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. tests/test_privileged_workflow_manual_admission_20261108.py |
| `reconcile/quarantine-exact-environment-replay-20261108-r1` | `c32384349f` | 2026-11-10 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `reconcile/quarantine-frontier-approval-20261108-r1` | `c561bb06d6` | 2026-11-09 | nothing unique | superseded: its 13 remaining edits conflict with newer main versions |
| `reconcile/quarantine-game-agent-loop-20261108-r1` | `76c1fb9f7c` | 2026-11-09 | fully on main | every changed blob already on main |
| `reconcile/quarantine-gameplay-migration-20261108-r1` | `c8271f7a08` | 2026-11-09 | fully on main | every changed blob already on main |
| `reconcile/quarantine-gfm-qualification-20261108-r1` | `7c527d058d` | 2026-11-10 | fully on main | every changed blob already on main |
| `reconcile/quarantine-godot-export-20261108-r1` | `e3de189ad3` | 2026-11-09 | nothing unique | superseded: its 10 remaining edits conflict with newer main versions |
| `reconcile/quarantine-native-flight-20261108-r1` | `bf21c5388d` | 2026-11-09 | fully on main | every changed blob already on main |
| `reconcile/quarantine-native-godot-export-20261108-r1` | `7647f1debe` | 2026-11-09 | nothing unique | superseded: its 6 remaining edits conflict with newer main versions |
| `reconcile/quarantine-perfgate-20261108-r2` | `31d3907f3e` | 2026-11-09 | fully on main | every changed blob already on main |
| `reconcile/quarantine-playable-archetypes-20261108-r1` | `10c2e7d120` | 2026-11-10 | nothing unique | superseded: its 6 remaining edits conflict with newer main versions |
| `reconcile/quarantine-raycast-vehicle-20261108-r1` | `47ff624c96` | 2026-11-09 | nothing unique | superseded: its 7 remaining edits conflict with newer main versions |
| `reconcile/quarantine-sandbox-input-20261108-r1` | `4c8e3b30fe` | 2026-11-09 | fully on main | every changed blob already on main |
| `reconcile/remote-receipt-evidence-20261109-r06` | `db331d2706` | 2026-11-09 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `reconcile/review-six-source-sets-20261110` | `62dbfa2a1f` | 2026-11-11 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `reconcile/runtime-galaxy-security-archive-20261114-r04` | `c3b5dc9801` | 2026-11-16 | unique content pending port | 170 new files, 75 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5404 (conflicting) -> main; e.g. backend/core/core_v1/envelope.py, backend/core/core_v1/keys.py, backend/core/core_v1/secret_migration.py |
| `reconcile/scene-graph-iterative-editor-simulation-20261108-r01` | `5c22deec7c` | 2026-11-08 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. tests/test_flgb_transform_hierarchy_depth.py |
| `reconcile/scene-weather-deterministic-replay-20261114-r01` | `4ea2d25ca0` | 2026-11-15 | fully on main | every changed blob already on main |
| `reconcile/setup-observation-stale-20261109-r08` | `2e41950503` | 2026-11-09 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `reconcile/source-convergence-exact-head-qualification-20261108-r01` | `f151593d90` | 2026-11-08 | unique content pending port | 19 new files, 7 modified files survive a 3-way merge; 68 paths already carried by port PRs; e.g. .github/workflows/jeeves-atomic-review-regression.yml, .github/workflows/vol249-250-research-reasoning.yml, skeleton/testing/test_installer_contract_failure_receipts.py |
| `reconcile/strict-compose-loopback-full-service-audit-20261108-r01` | `04c8b9e1ac` | 2026-11-08 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `reconcile/studio-b-cinder-combat-mass-20261114-r01` | `030e2c1513` | 2026-11-14 | fully on main | every changed blob already on main |
| `reconcile/studio-b-cinder-combat-recovery-20261114-r01` | `07f43475ec` | 2026-11-14 | fully on main | every changed blob already on main |
| `reconcile/studio-c-fair-stream-pressure-runtime-20261114-r01` | `d4d5868adc` | 2026-11-16 | fully on main | every changed blob already on main |
| `reconcile/studio-c-fair-stream-tail-custody-20261114-r01` | `59b0026dc6` | 2026-11-15 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `reconcile/studio-forge-board-export-20261114-r01` | `ad6726568d` | 2026-11-15 | fully on main | every changed blob already on main |
| `reconcile/studio-scene-regression-custody-20261113` | `b9e8529a4f` | 2026-11-14 | fully on main | every changed blob already on main |
| `reconcile/telemetry-wiring-privacy-20261114-r02` | `bce1265e88` | 2026-11-15 | fully on main | every changed blob already on main |
| `reconcile/v6-nine-p0-verticals-20261109` | `eb45c11d9b` | 2026-11-10 | fully on main | every changed blob already on main |
| `reconcile/v6-seven-custody-and-setup-20261109` | `4130d5cc18` | 2026-11-10 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `recover/intelligence-context-custody-20261114` | `183c1c277b` | 2026-11-14 | fully on main | every changed blob already on main |
| `recover/realtime-sev2-hardening-20261114` | `9d60b38357` | 2026-11-15 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `recover/setup-cross-platform-20261114` | `dc98b87981` | 2026-11-14 | unique content pending port | 2 new files, 1 modified files survive a 3-way merge; e.g. frontend/scripts/test-setup-host-commands.cjs, frontend/src/features/Setup/setupCommands.ts |
| `recover/studio-build-flow-ux-20261114` | `ac34bc4eb9` | 2026-11-14 | unique content pending port | 4 new files, 7 modified files survive a 3-way merge; e.g. frontend/scripts/skeleton-forge/studio-build-flow-ux.test.cjs, frontend/src/skeletonForge/components/ScaledText.tsx, frontend/src/skeletonForge/components/foundation/PlayHandoffCard.tsx |
| `recovery/dirty102-code-state-gb20-spine-skeleton-20261107-202239-9bc760` | `71948d8c4c` | 2026-11-07 | fully on main | 2026-11-14 audit: ALREADY ON MAIN |
| `recovery/dirty102-code-state-is-guard-20261107-202211-df7e78` | `b2939b9d34` | 2026-11-07 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. skeleton/testing/test_cortex_guard_fail_closed.py |
| `recovery/dirty102-code-state-is-seal-20261107-202213-4d9bca` | `06f6c656fe` | 2026-11-07 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `recovery/dirty102-code-state-pg-20261107-202222-27d05d` | `25908283c8` | 2026-11-07 | nothing unique | superseded: its 10 remaining edits conflict with newer main versions |
| `recovery/dirty102-code-state-qs-20261107-202753-125954` | `064c3d2fde` | 2026-11-07 | nothing unique | superseded: its 17 remaining edits conflict with newer main versions |
| `recovery/dirty102-code-state-rt-20261107-202225-aa3eb2` | `369cc48620` | 2026-11-07 | nothing unique | superseded: its 43 remaining edits conflict with newer main versions |
| `recovery/dirty102-code-state-sk-20261107-202754-1f063d` | `7367f8a120` | 2026-11-07 | unique content pending port | 0 new files, 2 modified files survive a 3-way merge |
| `recovery/dirty102-code-state-sk-t1-20261107-202228-459f34` | `64c54812fb` | 2026-11-07 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `recovery/dirty102-code-state-sk4167-20261107-202225-00b2bd` | `fe51786384` | 2026-11-07 | nothing unique | superseded: its 12 remaining edits conflict with newer main versions |
| `recovery/dirty102-code-state-skeleton-20261107-202210-bda12a` | `b6de71dccb` | 2026-11-07 | nothing unique | 2026-11-14 audit: SKIP (cortex guarded; uv.lock) |
| `recovery/dirty102-code-state-skeleton-f3-20261107-202210-7e0632` | `e9e6b923f5` | 2026-11-07 | fully on main | 2026-11-14 audit: ALREADY ON MAIN |
| `recovery/dirty102-code-state-skeleton-f4-20261107-202211-50b11f` | `803c5d0cbf` | 2026-11-07 | fully on main | 2026-11-14 audit: ALREADY ON MAIN |
| `recovery/dirty102-code-state-skeleton-nsoh-hygiene20-20261107-202237-dce455` | `5ca1af8218` | 2026-11-07 | nothing unique | 2026-11-14 audit: SKIP (CI workflow pins on a 5588-behind base; DevOps-owned, not backend; removals not carried) |
| `recovery/dirty102-code-state-skeleton-olly-pack-j-20261107-202241-d637f0` | `47465c4ea1` | 2026-11-07 | nothing unique | 2026-11-14 audit: SKIP (shim port of legacy backend/core modules frozen under #4122; imports core.* / core.databases / emergentintegrations; saga_registry already at skeleton/ai/runtime/kernel) |
| `recovery/dirty102-code-state-skeleton-omni-20261107-202212-4bba11` | `c2caa2af18` | 2026-11-07 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `recovery/dirty102-code-state-skeleton-outbox-20261107-202211-9bc509` | `8c9f2a6e49` | 2026-11-07 | nothing unique | 2026-11-14 audit: SKIP (forge outbox+tests already on main; root uv.lock would alter dependency resolution) |
| `recovery/dirty102-code-state-skeleton-pr25-sota-20261107-202227-b0bada` | `8f8459b04e` | 2026-11-07 | nothing unique | 2026-11-14 audit: SKIP (cortex-guarded; 9439 behind) |
| `recovery/dirty102-code-state-skeleton-roger-20261107-202322-fa2bab` | `14f1a1c28a` | 2026-11-07 | nothing unique | 2026-11-14 audit: SKIP (root uv.lock would alter dependency resolution) |
| `recovery/dirty102-code-state-skeleton-stu-tools-20261107-202240-4f2d0a` | `6919c292bc` | 2026-11-07 | fully on main | 2026-11-14 audit: ALREADY ON MAIN |
| `recovery/dirty102-code-state-skeleton-willy-b025-20261107-202229-e1a357` | `b37861b9ec` | 2026-11-07 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. uv.lock |
| `recovery/dirty102-code-state-skeleton-willy-gfc-20261107-202223-1cece7` | `142279a419` | 2026-11-07 | unique content pending port | 3 new files, 1 modified files survive a 3-way merge; e.g. tests/test_gf_p0_15_model_readiness.py, tests/test_gf_p0_18_resource_envelope.py, uv.lock |
| `recovery/dirty102-code-state-skmain-20261107-202226-f4488c` | `7b91a86915` | 2026-11-07 | fully on main | every changed blob already on main |
| `recovery/dirty102-code-state-wt-4253-20261107-202213-35fcc9` | `e6860a3d7c` | 2026-11-07 | unique content pending port | 1 new files, 1 modified files survive a 3-way merge; e.g. tests/adv.py |
| `recovery/dirty102-deletion-heavy-state-sk-cli-e2e-20261107-202333-4ac957` | `97e8022d83` | 2026-11-07 | unique content pending port | stale snapshot; a few additive files not on main: frontend/components/BootLauncher.tsx, frontend/components/ErrorBoundary.tsx, frontend/components/LaunchCascade.tsx, frontend/components/OfflineBanner.tsx, frontend/components/RecentArtifactsStrip.tsx, frontend/components/primitives/Button.tsx, frontend/components/withScreenGuard.tsx, frontend/consta |
| `recovery/dirty102-deletion-heavy-state-skeleton-20261107-202315-a77d74` | `aed52fb4ec` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-heavy-state-skeleton-20261107-202332-446c7c` | `9a13174425` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-heavy-state-skeleton-aervid-20261107-202305-39e4d0` | `89b13a7aad` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-heavy-state-skeleton-b021-20261107-202241-87eb6e` | `9c622bbccc` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-heavy-state-skeleton-bork-20261107-202315-ede329` | `4279afa57f` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-heavy-state-skeleton-char-polish-api-20261107-202333-eb0ed3` | `fd94a1cf95` | 2026-11-07 | unique content pending port | stale snapshot; a few additive files not on main: frontend/components/BootLauncher.tsx, frontend/components/ErrorBoundary.tsx, frontend/components/LaunchCascade.tsx, frontend/components/OfflineBanner.tsx, frontend/components/RecentArtifactsStrip.tsx, frontend/components/primitives/Button.tsx, frontend/components/withScreenGuard.tsx, frontend/consta |
| `recovery/dirty102-deletion-heavy-state-skeleton-cos-b023-20261107-202325-101d2a` | `931aeaf923` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-heavy-state-skeleton-cos-export-20261107-202325-636db1` | `de4619618a` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-heavy-state-skeleton-cos-export-20261107-202951-c17b48` | `a3a90cde60` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-heavy-state-skeleton-cos-forge2-20261107-202257-9e823f` | `0a0fb03fe1` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-heavy-state-skeleton-cos-land-20261107-202324-154f50` | `dd4d71b5dd` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-heavy-state-skeleton-cos-ui2-20261107-202332-da5e20` | `1a829f933f` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-heavy-state-skeleton-github-ops-20261107-202324-a7a5d2` | `a9d91b97bd` | 2026-11-07 | unique content pending port | stale snapshot; a few additive files not on main: core/shift_supervisor/assurance_context_test.py, core/shift_supervisor/assurance_model_boundary_test.py, frontend/components/BootLauncher.tsx, frontend/components/ErrorBoundary.tsx, frontend/components/LaunchCascade.tsx, frontend/components/ModalErrorBoundary.tsx, frontend/components/OfflineBanner.t |
| `recovery/dirty102-deletion-heavy-state-skeleton-glenny-20261107-202322-ae8b55` | `73ad6e507e` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-heavy-state-skeleton-gronk-20261107-202312-66fa62` | `f6d87e8998` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-heavy-state-skeleton-internal-systems-20261107-202313-0f72a7` | `a5e6263300` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-heavy-state-skeleton-is-next-20261107-202304-dea62f` | `a5ddff7eeb` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-heavy-state-skeleton-klappo-20261107-202313-39ee8b` | `945c12692f` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-heavy-state-skeleton-martinus-20261107-202313-61f5ca` | `df7bf56a15` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-heavy-state-skeleton-middleware-20261107-202321-5519a6` | `18fc4bef55` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-heavy-state-skeleton-olly-cockpit-ops-20261107-202304-bf6115` | `1db94137a3` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-heavy-state-skeleton-oyvind-20261107-202334-59e77e` | `01dd1a7edd` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-heavy-state-skeleton-pack-g2-20261107-202305-e0989b` | `523f516e6f` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-heavy-state-skeleton-packh-20261107-202250-4acf51` | `43f1d6ad29` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-heavy-state-skeleton-shirt-4-20261107-202334-f274da` | `2510b785f3` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-heavy-state-skeleton-willy-20261107-202323-0b4371` | `964863024f` | 2026-11-07 | unique content pending port | stale snapshot; a few additive files not on main: frontend/components/BootLauncher.tsx, frontend/components/ErrorBoundary.tsx, frontend/components/LaunchCascade.tsx, frontend/components/OfflineBanner.tsx, frontend/components/RecentArtifactsStrip.tsx, frontend/components/primitives/Button.tsx, frontend/components/withScreenGuard.tsx, frontend/consta |
| `recovery/dirty102-deletion-heavy-state-snappo-skel-20261107-202334-925bbe` | `91ae3e0948` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-state-sk-pre2006-20261107-202249-a073ef` | `578c878fe8` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-state-skeleton-20261107-202256-3853b5` | `ab20cb0bda` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-state-skeleton-ashbro-loop-20261107-202305-e4fa30` | `3238197e30` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-state-skeleton-backend-20261107-202315-f062db` | `e251874c2c` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-state-skeleton-char-polish-20261107-202249-382618` | `25e14ffa04` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-state-skeleton-coder-lead-20261107-202239-fd85e5` | `ad7cacfac3` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-state-skeleton-coder-lead-20261107-202306-32fc6f` | `a0c7e6d934` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-state-skeleton-cos-ci-20261107-202249-d0054b` | `7ae278df36` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-state-skeleton-cos-ci2-20261107-202257-2d342e` | `36c5cb4e10` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-state-skeleton-cos-fe-20261107-202249-601263` | `0dbd2e99ef` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-state-skeleton-cos-sandbox-20261107-202249-a29d7d` | `749b979e66` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-state-skeleton-cos-tests-20261107-202250-70ba01` | `34d7a0b3e5` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-state-skeleton-devops-diag-20261107-202249-9dd1c8` | `c426bfbd73` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-state-skeleton-is-pack-c-20261107-202239-f3172f` | `bc1a8b1b23` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-state-skeleton-nsoh-merkle20-20261107-202237-42d56f` | `9b1a4405bb` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-state-skeleton-walt-20261107-202313-0ec143` | `48b5fc88f6` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-state-stu-e2e-20261107-202304-354b21` | `b19d6b5c8c` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-state-wt-0fac6f97-20261107-202256-3873e6` | `9c4d11845e` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-state-wt-44cf573f-20261107-202256-8268d3` | `8171311316` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-state-wt-6609e1ea-20261107-202256-44ab53` | `3a05ff225f` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-state-wt-772dd40b-20261107-202256-b05601` | `c0ecc83eb6` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-state-wt-be4e63d9-20261107-202257-e091b9` | `e70830aca4` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty102-deletion-state-wt-packf-20261107-202304-6042ae` | `51cfeb40eb` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty91-carrol-gfm-20261107-192241-547443` | `347ee8a867` | 2026-11-07 | nothing unique | superseded: its 10 remaining edits conflict with newer main versions |
| `recovery/dirty91-frontend-b019-20261107-192241-436e01` | `5d088100cc` | 2026-11-07 | nothing unique | superseded: its 5 remaining edits conflict with newer main versions |
| `recovery/dirty91-frontend-gf-20261107-192241-714eb6` | `eea8c26325` | 2026-11-07 | nothing unique | superseded: its 5 remaining edits conflict with newer main versions |
| `recovery/dirty91-g4256-20261107-200603-a4413a` | `3de94d3297` | 2026-11-07 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `recovery/dirty91-gl-jv-20261107-192241-644d7c` | `aed4d91a59` | 2026-11-07 | fully on main | every changed blob already on main |
| `recovery/dirty91-pr4097-20261107-200605-875385` | `a686a354b5` | 2026-11-07 | nothing unique | superseded: its 21 remaining edits conflict with newer main versions |
| `recovery/dirty91-proj-20261107-200604-2c32b4` | `d0bdd50c1b` | 2026-11-07 | nothing unique | superseded: its 8 remaining edits conflict with newer main versions |
| `recovery/dirty91-sk-gfm-20261107-200602-5e58da` | `02d9e0c229` | 2026-11-07 | nothing unique | superseded: its 11 remaining edits conflict with newer main versions |
| `recovery/dirty91-skeleton-media-lafs-deepen-20261107-200415-56b1fe` | `8b15393d4b` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty91-skeleton-olly-4169-20261107-192241-9a4fbc` | `9d3e1a4798` | 2026-11-07 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `recovery/dirty91-skeleton-olly-coalesce-20261107-200415-e6f3d3` | `1fcf2397a7` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/dirty91-skeleton-smoke-20261107-200601-37295a` | `afb7d21386` | 2026-11-07 | nothing unique | deletion-dominant stale snapshot; additive files are old workflows, media/DB dumps or code relocated under frontend/src and skeleton/ai |
| `recovery/gameplay-save-migration-045fb104-20261107-184724` | `045fb10489` | 2026-10-31 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `recovery/godot-export-certification-7c5941dc-20261107-184724` | `ad9363bd87` | 2026-11-08 | nothing unique | superseded: its 7 remaining edits conflict with newer main versions |
| `recovery/pr4853-pre-rebase-20261110` | `a186274be3` | 2026-11-09 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `recovery/pr5017-pre-rebase-20261110` | `d7a83e536b` | 2026-11-09 | unique content pending port | 9 new files, 52 modified files survive a 3-way merge; 1 paths already carried by port PRs; e.g. skeleton/testing/test_game_project_cli_custody.py, skeleton/testing/test_game_project_cli_input_budget.py, skeleton/testing/test_godot_export_cli_custody.py |
| `recovery/pr5020-pre-rebase-20261110` | `05f1c9ae2f` | 2026-11-10 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `recovery/pr5057-pre-rebase-20261110` | `779ed662fd` | 2026-11-10 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `recovery/pr5064-pre-rebase-20261110` | `38119df313` | 2026-11-08 | unique content pending port | 9 new files, 52 modified files survive a 3-way merge; 1 paths already carried by port PRs; e.g. skeleton/testing/test_game_project_cli_custody.py, skeleton/testing/test_game_project_cli_input_budget.py, skeleton/testing/test_godot_export_cli_custody.py |
| `recovery/pr5067-pre-rebase-20261110` | `c8efe47a24` | 2026-11-09 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `recovery/pr5095-pre-rebase-20261110` | `0d291578a1` | 2026-11-10 | nothing unique | superseded: its 6 remaining edits conflict with newer main versions |
| `recovery/pr5097-pre-rebase-20261110` | `d77e51b0ee` | 2026-11-10 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. skeleton/testing/test_jeeves_export_verification_custody.py |
| `recovery/pr5107-original-20261109-0329` | `56ceddd21f` | 2026-11-09 | nothing unique | superseded: its 6 remaining edits conflict with newer main versions |
| `recovery/pr5122-original-20261109-0329` | `6f92160c0b` | 2026-11-09 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `recovery/pr5127-pre-main-20261109` | `2ce813fa51` | 2026-11-09 | nothing unique | superseded: its 10 remaining edits conflict with newer main versions |
| `recovery/pr5129-pre-main-20261109` | `3954c9b878` | 2026-11-09 | fully on main | every changed blob already on main |
| `recovery/pr5130-pre-main-20261109` | `320028e32a` | 2026-11-09 | fully on main | every changed blob already on main |
| `recovery/pr5175-pre-rebase-20261110` | `8f9e24dd7a` | 2026-11-10 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `recovery/pre-mainfirst-dragon-ci-budget-20261113-r8` | `c1ddf8fc2f` | 2026-11-09 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `recovery/pre-mainfirst-dragon-delivery-exceptions-20261113-r4` | `0b52921d83` | 2026-10-24 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `recovery/pre-mainfirst-dragon-traceability-20261113-r3` | `e557da34e5` | 2026-10-23 | fully on main | every changed blob already on main |
| `recovery/pre-mainfirst-frontier-m13-20261113-r3` | `e47741a67b` | 2026-10-23 | fully on main | every changed blob already on main |
| `recovery/pre-mainfirst-game-continuity-20261113-r7` | `0f0643d98c` | 2026-10-23 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `recovery/pre-mainfirst-game-delivery-seven-20261113-r10` | `f94ba97e0e` | 2026-10-23 | nothing unique | superseded: its 6 remaining edits conflict with newer main versions |
| `recovery/pre-mainfirst-game-mechanics-50-20261113-r6` | `65c4f9f693` | 2026-11-05 | fully on main | every changed blob already on main |
| `recovery/pre-mainfirst-game-production-seven-gates-20261113-r14` | `3edf96aa65` | 2026-10-23 | nothing unique | superseded: its 280 remaining edits conflict with newer main versions |
| `recovery/pre-mainfirst-gamebuilder-e2e-20261113-r5` | `7a893572ea` | 2026-10-31 | fully on main | every changed blob already on main |
| `recovery/pre-mainfirst-gameforge-smoke-20261113-r9` | `d76ac3e369` | 2026-10-17 | nothing unique | superseded: its 9 remaining edits conflict with newer main versions |
| `recovery/pre-mainfirst-jeeves-adaptive-20261113-r11` | `486ea03ae2` | 2026-10-20 | nothing unique | superseded: its 10 remaining edits conflict with newer main versions |
| `recovery/pre-mainfirst-jeeves-book-weights-20261113-r3` | `8343a17e0f` | 2026-10-23 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `recovery/pre-mainfirst-jeeves-game-cli-20261113-r13` | `936ec83a63` | 2026-10-16 | nothing unique | superseded: its 17 remaining edits conflict with newer main versions |
| `recovery/pre-mainfirst-jeeves-model-inventory-20261113-r12` | `e23ecfcf36` | 2026-10-16 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `recovery/pre-mainfirst-nodeforge-pr5280-20261113-r1` | `cd7d907eee` | 2026-11-12 | ported in PR #5771 | all 0 new / 1 modified surviving paths are carried by the port |
| `recovery/pre-mainfirst-pr5288-frontier-native-20261113-r1` | `e4544d7946` | 2026-11-13 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `recovery/pre-rebase-admission-lease-20261113` | `68ee3927a7` | 2026-11-05 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `recovery/pre-rebase-dragon-archives-20261113-r2` | `50f3ac7757` | 2026-11-09 | unique content pending port | 0 new files, 2 modified files survive a 3-way merge |
| `recovery/pre-rebase-game-frontier-20261113-r2` | `df74a924dc` | 2026-10-25 | unique content pending port | 2 new files, 0 modified files survive a 3-way merge; e.g. artifacts/coder-lead/status-20261024-1847.md, artifacts/coder-lead/status-20261024-1905.md |
| `recovery/pre-rebase-jeeves-book-studio-20261113-r2` | `95ba277c94` | 2026-10-23 | nothing unique | superseded: its 9 remaining edits conflict with newer main versions |
| `recovery/pre-rebase-jeeves-native-r87-20261113-r2` | `b71eae91c8` | 2026-11-05 | nothing unique | superseded: its 149 remaining edits conflict with newer main versions |
| `recovery/pre-rebase-jeeves-native-r88-20261113-r2` | `7875b796a9` | 2026-11-05 | nothing unique | superseded: its 148 remaining edits conflict with newer main versions |
| `recovery/pre-rebase-jeeves-native-r89-20261113-r2` | `753dc82a25` | 2026-11-05 | nothing unique | superseded: its 148 remaining edits conflict with newer main versions |
| `recovery/sandbox-guard-executor-e310c97c-20261107-184724` | `e310c97cf8` | 2026-10-24 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `refactor/frontend-single-src-tree` | `e66e67dd3b` | 2026-10-18 | nothing unique | superseded: its 31 remaining edits conflict with newer main versions |
| `repair/4348-provider-context-pair-20261027` | `7533582e68` | 2026-10-27 | unique content pending port | 0 new files, 4 modified files survive a 3-way merge |
| `repair/ci-first-install-consolidated-20261108-b03` | `7c03a2ea19` | 2026-11-10 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `repair/ci-game-source-and-fixtures-20261108-b02` | `12f61c0cfd` | 2026-11-08 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `repair/ci-shared-contracts-20261108-b01` | `a021c4bd73` | 2026-11-08 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `repair/ci-tier-duplicate-trigger-20261121` | `0dd37bd228` | 2026-11-21 | unique content pending port | 4 new files, 28 modified files survive a 3-way merge; open PR #5739 (mergeable) -> repair/ci-tier-duplicate-workflow-20261120; e.g. docs/creation/PLOT_BEATS.md, skeleton/ai/agents/jeeves/plot_beats.py, skeleton/ai/forge/media_depth/__init__.py |
| `repair/ci-tier-duplicate-workflow-20261120` | `75b542b3f9` | 2026-11-20 | unique content pending port | 4 new files, 28 modified files survive a 3-way merge; open PR #5738 (mergeable) -> repair/pr5694-native-proof-20261120; e.g. docs/creation/PLOT_BEATS.md, skeleton/ai/agents/jeeves/plot_beats.py, skeleton/ai/forge/media_depth/__init__.py |
| `repair/ci-tier-event-duplicate-20261121` | `7275a15ecf` | 2026-11-21 | unique content pending port | 4 new files, 28 modified files survive a 3-way merge; open PR #5741 (mergeable) -> repair/ci-tier-trigger-regex-20261121; e.g. docs/creation/PLOT_BEATS.md, skeleton/ai/agents/jeeves/plot_beats.py, skeleton/ai/forge/media_depth/__init__.py |
| `repair/ci-tier-trigger-regex-20261121` | `7093142227` | 2026-11-21 | unique content pending port | 4 new files, 28 modified files survive a 3-way merge; open PR #5740 (mergeable) -> repair/ci-tier-duplicate-trigger-20261121; e.g. docs/creation/PLOT_BEATS.md, skeleton/ai/agents/jeeves/plot_beats.py, skeleton/ai/forge/media_depth/__init__.py |
| `repair/expo54-lockfile-20261027` | `33a771793c` | 2026-10-28 | unique content pending port | 0 new files, 4 modified files survive a 3-way merge |
| `repair/first-install-redaction-cas-20261108-b01` | `b3208ba3c3` | 2026-11-10 | nothing unique | superseded: its 67 remaining edits conflict with newer main versions |
| `repair/pr5694-native-proof-20261120` | `bfbef83a42` | 2026-11-20 | unique content pending port | 4 new files, 26 modified files survive a 3-way merge; open PR #5737 (mergeable) -> feat/plot-beats; e.g. docs/creation/PLOT_BEATS.md, skeleton/ai/agents/jeeves/plot_beats.py, skeleton/ai/forge/media_depth/__init__.py |
| `repair/pr5694-surface-digests-20261120` | `1f106c35f7` | 2026-11-20 | unique content pending port | 4 new files, 24 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5736 (mergeable) -> feat/plot-beats; e.g. docs/creation/PLOT_BEATS.md, skeleton/ai/agents/jeeves/plot_beats.py, skeleton/ai/forge/media_depth/__init__.py |
| `review/backend-quality-eight-pr-source-convergence-20261110-r01` | `adc2fcd901` | 2026-11-10 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `security/codeql-ci-qualification-20261111` | `98b8e2a16d` | 2026-11-11 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `security/codeql-continuation-20261111` | `813f457399` | 2026-11-11 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `security/codeql-explicit-5xx-boundary-20261111` | `a709dd33dc` | 2026-11-11 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `security/codeql-share-csp-postmerge-20261111` | `bf247c46d8` | 2026-11-11 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `security/codeql-stack-exception-boundary-20261111` | `6a780a4bcb` | 2026-11-11 | nothing unique | superseded: its 5 remaining edits conflict with newer main versions |
| `security/hold-gate-and-telemetry-custody-20261111` | `2598e7ba86` | 2026-11-12 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `security/lock-dispatch-qualification-to-main-20261111` | `f8d9af6b24` | 2026-11-11 | fully on main | every changed blob already on main |
| `security/remediate-codeql-root-causes-20261111` | `ad9d6b3d2f` | 2026-11-11 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `security/tenant-bound-binary-vault-telemetry-20261111` | `304dd5ba28` | 2026-11-11 | nothing unique | superseded: its 17 remaining edits conflict with newer main versions |
| `sota-augments-10x-drafts-20261022` | `87630156ef` | 2026-10-22 | unique content pending port | 3 new files, 0 modified files survive a 3-way merge; e.g. docs/SOTA_AUGMENTS_10X.md, skeleton/augments/__init__.py, skeleton/augments/organ_00.py |
| `sota-augments-milestones-20261022` | `356c573b2d` | 2026-10-22 | unique content pending port | 3 new files, 0 modified files survive a 3-way merge; e.g. docs/SOTA_AUGMENTS_20261022.md, skeleton/augments/__init__.py, skeleton/augments/clipped_mass.py |
| `stability/crash-foundation-20261017` | `9523dcaf53` | 2026-10-17 | nothing unique | superseded: its 23 remaining edits conflict with newer main versions |
| `stability/crash-recovery-2026-10-17` | `f9b117038f` | 2026-10-17 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `studio-a-v6-scenegraph-iterative-cycle-20261108` | `65def678ba` | 2026-11-08 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `studio-a-v6-world-source-hardlink-custody-20261108` | `39ef62bc73` | 2026-11-09 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `studio-a/20261109-adventure-graph-reachability` | `8f1dbf4ddf` | 2026-11-09 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `studio-a/iterative-scene-validation-20261108` | `302e32880e` | 2026-11-09 | fully on main | every changed blob already on main |
| `studio-a/laptop-recovery-guard-regressions-20261105` | `b5c6760849` | 2026-11-06 | nothing unique | superseded: its 3 remaining edits conflict with newer main versions |
| `studio-a/v6-20261108-graph-depth-failclosed` | `64896fc49a` | 2026-11-08 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. tests/test_jeeves_deep_authoring_graph.py |
| `studio-a/v6-browser-save-replay-20261107-2101` | `efa1b4c95c` | 2026-11-07 | unique content pending port | 1 new files, 1 modified files survive a 3-way merge; e.g. skeleton/testing/test_jeeves_browser_save_contract.py |
| `studio-a/v6-creator-cli-strict-json-20261108` | `fe13fc8f11` | 2026-11-08 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. tests/forge_ai_builder/test_creator_cli_json_ingress.py |
| `studio-a/v6-keyboard-player-20261107-2001` | `4646694e18` | 2026-11-09 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `studio-a/v6-prefab-deep-validation-20261109-1510` | `d5275f6cff` | 2026-11-13 | fully on main | 0 commits ahead |
| `studio-a/v6-scene-graph-deep-cycle-20261108-1157` | `b3c199b38e` | 2026-11-09 | fully on main | every changed blob already on main |
| `studio-a/v6-scene-graph-iterative-20261108-1500` | `2b94826a04` | 2026-11-08 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `studio-a/v6-scene-graph-iterative-validation-20261108` | `a31f737325` | 2026-11-08 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `studio-a/v6-scenegraph-deep-cycle-20261109` | `ab96151c82` | 2026-11-09 | fully on main | every changed blob already on main |
| `studio-a/v6-scenegraph-deep-tree-20261108-0700` | `1a587a309b` | 2026-11-08 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `studio-a/v6-session-snapshot-lease-20261109` | `9e6c167292` | 2026-11-09 | fully on main | every changed blob already on main |
| `studio-a/v6-world-export-custody-20261108-0558` | `9b0280b2a1` | 2026-11-08 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `studio-a/v6-world-playthrough-proof-20261108` | `1a40c47574` | 2026-11-09 | fully on main | every changed blob already on main |
| `studio-b-v6-20261108-transform-depth` | `b39113d47d` | 2026-11-09 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `studio-b-v6-godot-engine-pin-failclosed-20261109` | `58ac3a57f5` | 2026-11-09 | fully on main | every changed blob already on main |
| `studio-b-v6-replay-ratio-bounds-20261108-0216` | `25357fbe8a` | 2026-11-09 | fully on main | every changed blob already on main |
| `studio-b/fix-controller-step-bounds-20261109` | `732a10c099` | 2026-11-09 | unique content pending port | 1 new files, 1 modified files survive a 3-way merge; e.g. tests/test_game_controller_bounds.py |
| `studio-b/v6-20261108-atomic-grid-save` | `dc1c94143b` | 2026-11-08 | fully on main | every changed blob already on main |
| `studio-b/v6-20261109-grid-terminal-player` | `87371be706` | 2026-11-09 | ported in PR #5779 |  |
| `studio-b/v6-atomic-offline-grid-save-20261107` | `5482782c3a` | 2026-11-09 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `studio-b/v6-command-input-contract-20261108-2018` | `d994f27a52` | 2026-11-08 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `studio-b/v6-deep-transform-20261108-0716` | `fb7e83785d` | 2026-11-08 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. tests/test_flgb_transform_hierarchy_depth.py |
| `studio-b/v6-export-artifact-verification-20261108` | `6e6f83b8a5` | 2026-11-09 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `studio-b/v6-fixed-clock-restart-20261109-11` | `8da3dee8b2` | 2026-11-09 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. tests/test_game_fixed_clock.py |
| `studio-b/v6-gameplay-input-20261108-0516` | `de78fdce7f` | 2026-11-09 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `studio-b/v6-goal-route-20261109-0116` | `38146700bc` | 2026-11-09 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `studio-b/v6-godot-headless-play-acceptance-20261108` | `fa7ebf8f55` | 2026-11-08 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `studio-b/v6-godot-resource-boundary-20261108` | `0ea06f6300` | 2026-11-09 | fully on main | every changed blob already on main |
| `studio-b/v6-golden-grid-replay-20261108-0016` | `ddf5577dd6` | 2026-11-09 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `studio-b/v6-grid-atomic-save-20261107-2116` | `dce741a79c` | 2026-11-09 | fully on main | every changed blob already on main |
| `studio-b/v6-grid-atomic-save-20261108-1219` | `4dab0cb811` | 2026-11-08 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. tests/game/test_grid_save_custody.py |
| `studio-b/v6-grid-durable-save-20261108-2316` | `ddd36a36b5` | 2026-11-08 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `studio-b/v6-prefab-depth-20261108-1518` | `33331ed2d6` | 2026-11-08 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. tests/test_game_prefab_inheritance_depth_v6.py |
| `studio-b/v6-replay-checkpoint-20261109-1116` | `af161a7b70` | 2026-11-10 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `studio-c/gguf-model-custody-20261108-0131` | `0b5aaf03d4` | 2026-11-10 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `studio-c/local-compose-loopback-20261109` | `72d9e0194e` | 2026-11-09 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. tests/integration/test_compose_local_ports.py |
| `studio-c/v6-fail-closed-gguf-loader-20261108-2027` | `3b5479308f` | 2026-11-08 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `studio-c/v6-fail-closed-local-ai-readiness-20261108` | `e9aac96cb3` | 2026-11-09 | nothing unique | superseded: its 15 remaining edits conflict with newer main versions |
| `studio-c/v6-local-ai-readiness-truth-20261108` | `1ca65f7443` | 2026-11-08 | fully on main | every changed blob already on main |
| `studio-c/v6-native-profile-finite-custody-20261108` | `556984e957` | 2026-11-09 | fully on main | every changed blob already on main |
| `studio-c/v6-token-batch-bounded-20261108-2335` | `effec3c35a` | 2026-11-08 | fully on main | every changed blob already on main |
| `studio-c/v6-wire-payload-bounds-20261108` | `3b5d50e78c` | 2026-11-09 | nothing unique | superseded: its 4 remaining edits conflict with newer main versions |
| `studio-d/doctor-no-proxy-20261108-0449` | `61406e248d` | 2026-11-08 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. tests/test_studio_doctor_proxy_isolation.py |
| `studio-d/first-install-loopback-20261109` | `1590aa065e` | 2026-11-09 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `studio-d/first-install-provider-identity-20261108` | `8e4ec3a987` | 2026-11-09 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `studio-d/loopback-compose-20261108-0151` | `73596379a0` | 2026-11-09 | nothing unique | superseded: its 7 remaining edits conflict with newer main versions |
| `studio-d/loopback-compose-ports-20261108` | `ef937d20cf` | 2026-11-08 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `studio-d/loopback-first-install-20261107-2049` | `2921716f72` | 2026-11-07 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `studio-d/loopback-first-install-20261108` | `0c9255897b` | 2026-11-08 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `studio-d/loopback-first-install-20261108-run3` | `9fd17f4add` | 2026-11-08 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. tests/test_consumer_loopback_compose.py |
| `studio-d/loopback-first-install-ports-20261107` | `e271602e0d` | 2026-11-09 | nothing unique | superseded: its 6 remaining edits conflict with newer main versions |
| `studio-d/loopback-first-install-v6-20261108-1341` | `55f94e4ea4` | 2026-11-08 | nothing unique | superseded: its 2 remaining edits conflict with newer main versions |
| `studio-d/loopback-readiness-20261107-1544` | `99c188adb0` | 2026-11-09 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `studio-d/v6-health-redirect-no-follow-20261108` | `c62221a455` | 2026-11-09 | fully on main | every changed blob already on main |
| `studio-d/v6-local-compose-port-fence-20261109` | `5082a351a4` | 2026-11-09 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `studio-d/v6-local-loopback-compose-20261108` | `b2b13e95f7` | 2026-11-10 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `studio-d/v6-local-loopback-ports-20261108` | `0b522836a0` | 2026-11-08 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `studio-d/v6-loopback-compose-20261108-0046` | `7fe6d2cd75` | 2026-11-08 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `studio-d/v6-loopback-compose-20261108-0646` | `0962bd976b` | 2026-11-09 | unique content pending port | 2 new files, 0 modified files survive a 3-way merge; e.g. tests/test_compose_first_install_ai_tree_custody_20261108.py, tests/test_consumer_compose_bindings.py |
| `studio-d/v6-loopback-first-install-20261108` | `1607afb747` | 2026-11-08 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `studio-d/v6-loopback-first-install-20261108-0746` | `e0012e00ce` | 2026-11-08 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `studio-d/v6-loopback-port-fence-20261109-0749` | `9f126855dc` | 2026-11-09 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `studio-d/v6-readiness-account-outage-20261108` | `dfb1b2c6bd` | 2026-11-08 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `studio-d/v6-setup-offline-verdict-20261108-1748` | `97ad559957` | 2026-11-10 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `studio-d/v6-source-ref-zip-preflight-20261107-2243` | `df4c6374fe` | 2026-11-09 | fully on main | 3-way merge onto main is a no-op (ignoring deletions) |
| `studio-d/v6-windows-zip-special-file-admission-20261108` | `918aedf9ce` | 2026-11-09 | fully on main | every changed blob already on main |
| `studio-d/zip-entry-guard-20261108` | `831a07f124` | 2026-11-08 | unique content pending port | 0 new files, 1 modified files survive a 3-way merge |
| `test-readiness-integration` | `41645e732e` | 2026-11-05 | unique content pending port | 1 new files, 0 modified files survive a 3-way merge; e.g. tests/test_readiness_bridge.py |
| `test/emerald-v7-independent-binary-recheck-20261117` | `1aeb694202` | 2026-11-17 | unique content pending port | 175 new files, 12 modified files survive a 3-way merge; 1 paths already carried by port PRs; open PR #5589 (mergeable) -> feat/emerald-v7-qualified-offline-replay-20261117; e.g. .github/workflows/dragon-atelier-prototype.yml, .github/workflows/emerald-five-evolutions.yml, .github/workflows/emerald-poster-v4.yml |
| `test/laptop-real-sqlite-cold-reopen-fixture-20261104-r25` | `64cf8b90ab` | 2026-11-05 | nothing unique | superseded: its 171 remaining edits conflict with newer main versions |
| `test/native-flight-sigbus-stress-20261110-r01` | `e6d5c7e53e` | 2026-11-10 | unique content pending port | 12 new files, 54 modified files survive a 3-way merge; 1 paths already carried by port PRs; e.g. skeleton/testing/test_game_project_cli_custody.py, skeleton/testing/test_game_project_cli_input_budget.py, skeleton/testing/test_godot_export_cli_custody.py |
| `test/offline-game-custody-qualification-20261107` | `5315a2099e` | 2026-11-07 | unique content pending port | 1 new files, 2 modified files survive a 3-way merge; e.g. .github/workflows/jeeves-offline-game-custody-qualification.yml |
| `test/studio-authoritative-gameplay-final-20261030` | `7c17a0ea88` | 2026-10-30 | ported in PR #5767 | all 71 new / 0 modified surviving paths are carried by the port (18 test modules held: fail on source branch too) |
| `test/studio-complete-execution-chain-20261030` | `fdb35a3ca4` | 2026-10-30 | ported in PR #5767 | all 29 new / 0 modified surviving paths are carried by the port |
| `test/studio-final-walkable-tranche-20261030` | `c3f1727218` | 2026-10-30 | ported in PR #5767 | all 63 new / 0 modified surviving paths are carried by the port (13 test modules held: fail on source branch too) |
| `test/studio-private-production-e2e-20261030` | `9d6467e56c` | 2026-10-30 | ported in PR #5767 | all 39 new / 0 modified surviving paths are carried by the port (1 test modules held: fail on source branch too) |
| `test/traffic-dispatch-custody-regression-40062674483` | `dcb4c8c249` | 2026-10-24 | nothing unique | superseded: its 1 remaining edits conflict with newer main versions |
| `wip/studio-c-long-context-stable-read-20261101-r11` | `5e38ad3683` | 2026-11-02 | unique content pending port | 50 new files, 0 modified files survive a 3-way merge; e.g. docs/ai/LONG_CONTEXT_ADMISSION_BUNDLE.md, docs/ai/LONG_CONTEXT_ADMISSION_RACE_FENCE.md, docs/ai/LONG_CONTEXT_BUCKET_IDENTITY.md |
| `wip/studio-d-summary-boundary-20261102-r11` | `da598f4a84` | 2026-11-02 | unique content pending port | 3 new files, 0 modified files survive a 3-way merge; e.g. docs/studio/CONSUMER_RELEASE_EVIDENCE.md, skeleton/app/consumer_release_evidence.py, skeleton/testing/test_app_consumer_release_evidence.py |
