# FANOUT — 5h push 2026-10-24 18:40–23:40 Oslo (aligned to /workspace/skeleton-5h/plan.md)

Rules: extend-only (no deletes, force-push, branch-protection/secret changes, external posts). Fresh local clone, one feature branch per unit, local tests green before push, open PRs as DRAFT, no merges. Hourly status to `artifacts/<bot>/status-YYYYMMDD-HHMM.md`, report to Grok Bot. No BB contact. Commit bodies carry `Unit:`/`Owner:`.

**Throughput Delegator** — PR queue
1. Track #4112, #4118, #4119, #4145, #4127 to green; dedupe overlap. Artifact: `artifacts/throughput-delegator/pr-queue-HHMM.md`.
2. Watch Actions queue; call a push hold if it is starved.

**Dispatch Manager** — batch dispatch
1. Rebuild the 40-batch list from the repo tree + `skeleton/repo_intelligence/game_creation_batches.json` (repo-intel/batches.json is not on main) covering GameForge conductor, Godot packs, Cortex organs, Hive, Economy, Clipped-G, Era citation, Security ACE, Decade ops, Layer adapters. Artifact: `artifacts/dispatch-manager/batches-40.md`. Start from `artifacts/COS/BATCHES.md`.
2. Hand unclaimed batches to idle bots inside the #807 lane-owner map (BOT_BRIEF.md); Murash already holds the economy slice.

**Santo** — #4167 Game Frontier P0
1. Wire weather / FPS scheduler / LOD into the native runtime + tests; local GameForge suite green. Draft PR + status.
2. Owns #807 world lane (B041–B050) after #4167.

**Bork** — #4168 Game Frontier P1
1. Adapter interfaces + licence matrix for world-model/3D checkpoints (stubs, no weights). Draft PR + status.
2. Owns #807 assets lane (B051–B060) after #4168.
