# Unified original creator and quest playability — 2026-11-13

## Exact source parents

- GameForge design instrument / 158 choice taxonomy: PRs #5296 and #5300, `c97d09af50f982f1fa0a5ddaf91fafcd18d073af`.
- Constrained original quest + native Godot gameplay/HUD: PRs #5304 and #5310, `2d251506528aa646d70ceed9234d4f0627c64600`.
- Canonical main comparison base: `d5275f6cff2b660ec6b41455fedb51567b113ad5`.

## Implementation

Brings 16 nonoverlapping GameForge source files unchanged into the native quest branch, then merges five overlapped implementation paths: backend route, questionnaire display, questionnaire state/request reducer, typed request/response contract, ten-stage compiler. The merged questionnaire preserves simultaneous bounded design-axis edits, specialized genre choices, native Godot quest toggle and quest length. The merged runtime serializes operator-axis design edits and native quest proof independently.

## Invariants and caveats

Genre choices are mapped to canonical era IDs, not assertions of 158 separately complete engines. Default calls without design-axis or quest opts keep old behavior. Native quest requires the Godot target, forbids implicit selection, and retains bounds/receipt safeguards. No remote inference providers, dynamic model-code execution, silent location use, or removal of main controls.

## Qualifications

Review only, do not merge or release. Exact-head focused Python and Node regression suites, TS type checks, API smoke, source parity, security/malware/hygiene, Godot runtime, device and first-install acceptance remain necessary. Queued/skipped runs are not passes.

## Explicit two-way studio draft bridge (source-level addition)

- GameForge opens Galaxy only after its current questionnaire draft has been saved locally under a bounded, versioned, single-use handoff. The original vision, explicit ten-axis edits, answered beats, era options, and optional Godot quest settings are preserved.
- Galaxy Studio can explicitly return its current authored game vision and primary recognized genre. Returning to GameForge restores its prior settings and updates compatible genre/vision fields; it never launches a build automatically.
- Transfer is local-only AsyncStorage with a 20-minute validity window and a maximum 16 KiB serialized envelope. Invalid, stale, wrong-direction, and unsupported fields are rejected/filtered.
- **Limit**: Galaxy's 14+ production matrices and extended slider values are *not* naively mapped to the ten-axis Forge tensor. They remain in Galaxy Studio; this bridge does not claim fully shared cross-editor editing or complete world playability.
- Node regression: `frontend/scripts/skeleton-forge/creator-bridge.test.cjs`, with exact-head focused qualification in `.github/workflows/gameforge-creator-quest-convergence.yml`.
