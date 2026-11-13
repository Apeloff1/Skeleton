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
