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

## Advanced Galaxy editor continuity

The cross-editor transfer now preserves Galaxy's **fourteen actual matrix families**, narrative-phase values, primary and fused genre selections, all additional slider maps, classic controls, production options, style choices and authored text in a separate, bounded, on-device editor draft. The full local snapshot is versioned, checked for numeric ranges, bounded to 320 KiB, and expires after 30 days. The pure codec has an independent focused regression suite at `frontend/scripts/skeleton-forge/galaxy-draft-custody.test.cjs`. Reloading Galaxy restores these values unless the user explicitly changes them. GameForge receives only compatible vision/genre choices while its own ten-axis/beat/quest settings are restored; **the two editors retain different control semantics**, rather than falsely mapping fourteen families to ten axes.

All of this is source-level work pending exact-head frontend typechecking and on-device navigation checks; it is not yet certified as release-ready.

## Extended continuity, failure modes and exact-head assurance

- Direct two-editor navigation now serializes the complete accepted design handoff. The Galaxy-to-Forge navigation is not initiated until **both** the full Galaxy snapshot and the single-use Forge handoff complete their local writes. A write failure keeps Galaxy open and surfaces an error. Reentrant taps are blocked during handoff.
- Returning after a long Galaxy edit does not expire the Forge questionnaire that was already verified and consumed when the editor was opened. Any **new** handoff remains versioned and has a new 20-minute validity window.
- Galaxy's normal editor close also persists its advanced settings before navigation; an explicit **Save Galaxy draft on device** action preserves a snapshot without closing. Save failures prevent destructive close.
- Galaxy's large target-file slider (48K–1M), scale command and expanded-descriptions setting are now persisted alongside the fourteen real matrix families, narrative phase tensor, original genre fusion, production choices, style/animation preferences and hundred-plus extra sliders.
- Reopening GameForge shows the number of retained Galaxy matrix families and extra slider values on this device. Their controls remain available when Galaxy Studio is reopened, and are deliberately **not** assigned unrelated semantics in Forge's ten-axis tensor.
- The source-focused CI workflow checks out `github.event.pull_request.head.sha` (or `github.sha` when manually dispatched), verifies the checkout SHA, and runs Python, Node component, matrix stress and TypeScript qualifications. A completed pass on a synthetic pull request merge ref is not called exact-head qualification.
- No user build, device test, security certification or main merge is claimed by this ledger.
