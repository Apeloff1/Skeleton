# Backlog — ranked, live

This file is a concise repository-level view, not the authoritative issue database. GitHub issues and pull requests are the source of truth for exact state. The purpose of this page is to prevent the repository from incorrectly reporting “no backlog” while tracked work is still open.

## Delivered legacy backlog

The original 2026.09.05 backlog is complete:

1. ✅ Policy enforcement with dynamic thresholds and repair gating
2. ✅ Multi-pass repair autonomy with learned max-pass capping
3. ✅ Fault-tolerant repair telemetry
4. ✅ Learned repair policy with strategy suggestions
5. ✅ Repair orchestrator with unified entry point
6. ✅ Adaptive policy with self-tuning thresholds
7. ✅ Policy versioning with immutable snapshots and lineage
8. ✅ Policy rollback with preview and surface-targeting
9. ✅ Pixel lattice UI (HUD + editor layouts)
10. ✅ Octahedral KV cache (3D geometric eviction)
11. ✅ Live teacher mouth binding (viseme + blend shapes)
12. ✅ Parametric LoRA write-back (fusion + pruning + checkpoints)
13. ✅ GPU decoder prior (warp-aligned patches)
14. ✅ Advanced operator steering (64-dim composable vectors)

## Current tracked backlog — 2026-09-15

### P0 — security and merge enforcement

- **#540 — repository-wide security hardening and enforced merge gate.** Continue focused PRs for CI trust boundaries, source/runtime attack surface, secrets, dependency/container supply chain, security regressions, and operational readiness. Admin-only branch/ruleset enforcement remains a hard external dependency.
- **#127 — required checks and merge-readiness policy.** The stable merge-readiness workflow exists, but completion still depends on a successful canonical verification run and repository administration requiring the stable check on `main`.

### P1 — verification-complete implementation waiting on canonical CI evidence

- **#121 — observability contract.** Implementation acceptance is complete; keep open until canonical Merge Readiness succeeds on code containing the merged observability work.
- **#122 — cross-subsystem integration matrix.** Implementation acceptance is complete; keep open until canonical Merge Readiness succeeds on code containing the integration matrix.

### P1 — consolidation program

- **#80 — frontier repository consolidation program.** This remains the umbrella workstream. Completed subprojects should not be replayed from stale branches; remaining work should be promoted through focused, tested, provenance-aware changes.

## Working rules

- Prefer focused PRs over mega-diffs.
- Do not close verification-gated issues merely because implementation code exists; satisfy the stated evidence condition.
- Do not mark admin-only controls complete until repository settings actually enforce them.
- Do not replay stale branch names as backlog. Compare branch tips and patch content against current `main` first.
- Recovered/promoted code needs focused regression coverage and clear provenance.
- Keep security controls fail-closed; exceptions must be explicit, narrow, owned, and time-bounded.

## Candidate next directions after tracked issues

These are optional directions, not currently committed backlog:

1. On-chain helix consensus network (local jsonl only, no external chain)
2. Multi-agent swarm coordination protocols
3. Real-time telemetry streaming (WebSocket/SSE)
4. Automated benchmark regression suite
5. Cross-platform deployment packaging

## Laws that stay closed

- cite-do-not-copy, stored_prose scanned not stamped
- snowball mass 1.0 on ten stages
- hardware caps below the wall
- Import-time HuggingFace downloads — never this repo
- Steam / wiki prose on shelves — forbidden
- Hellas Reach / any repo other than Apeloff1/Skeleton — forbidden
