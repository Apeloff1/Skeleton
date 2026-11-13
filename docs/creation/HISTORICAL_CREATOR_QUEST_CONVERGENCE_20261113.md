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

## Offline tenant/session storage isolation

Cross-editor handoffs and full Galaxy drafts now use owner-scoped local AsyncStorage keys. The scope fingerprint comes from a local SHA-256 digest of the active bearer token after SecureStore/localStorage token initialization. **Raw bearer tokens are never used as draft keys, and draft persistence never performs a network lookup.** An anonymous session receives a separate anonymous namespace. Account epoch checks fence storage publication and consumption; stale data is unmounted when users log in or out. A scoped write that detects a concurrent account switch deletes its partial publication and fails closed.

This source-level isolation is exercised by `frontend/scripts/skeleton-forge/storage-scope.test.cjs`, which injects deterministic offline token, digest and storage mocks to verify Alice/Bob isolation, one-time consumption and auth changes during writes. Real device, reinstall, token renewal and hardware-specific recovery remain to be qualified. An intentionally conservative limitation is that rotating a bearer token also rotates its local key: this release does not migrate unscoped or differently scoped drafts without independently verified account continuity.

## Historical genre completeness and safe editor return

- The historical Galaxy offline fallback currently contains **69** distinct genre IDs, not the older 67 figure. `beat_em_up` and `shoot_em_up` had no GameForge mapping and are now explicitly mapped to the corresponding authorized `beat-em-up` and `shoot-em-up` genre votes.
- `creator-bridge.test.cjs` now enumerates every Galaxy fallback ID, requires exactly one valid GameForge genre choice for each ID, and verifies the resulting Forge build request. The old hard-coded 67-genre UI count was replaced by the actual catalog size, so future archive recoveries do not silently produce stale count labels.
- A live Galaxy genre that isn't in the offline fallback can still reach GameForge if its normalized ID exactly matches one of the 158 server-recognized genre tokens. Unsupported IDs produce a visible transfer error; they aren't silently replaced or dropped.
- Closing Galaxy after entering from Forge, without explicitly choosing Continue, reissues the **original accepted Forge questionnaire** as a fresh one-time handoff before navigating back. Galaxy edits are only applied through the explicit Continue action. Returning after a long editor session preserves already-consumed Forge beats, axes and quest options.
- Scoped handoff reads and writes are serialized per key in a single JavaScript runtime. Parallel consumers cannot claim the same message twice in that runtime. This does not claim a cross-process or multi-device atomic transaction; the offline AsyncStorage backend does not supply one. Corresponding concurrency and wrong-direction-reader regressions have been added.
- The full local draft and actual gameplay remain subject to exact-head CI and independent installed-device qualification. **69 Galaxy categories and 158 creative-brief labels do not equal 158 independently playable game engines**.

## Real playable archetype output and independent native qualification

The archive already contained three executable Godot 4 prototype scenes — `extraction`, `combat_loop`, and `pipeline` — under `skeleton/forge/archetype_content.py`. This integration now makes their **explicit** `playable_content` opt-in available from the GameForge questionnaire through `RunRequest`, the API route, and `GameForgeRun.execute`. For `auto`/vision archetypes the existing sidecar selection falls back to the extraction prototype. Each sidecar has a CharacterBody2D player controller, complete loop, and success/failure markers. All three are selectable *playable prototypes*, not proof that the entire 158-label taxonomy implements corresponding gameplay engines.

`playable_content` and the original native room-entry quest may be enabled together for a Godot project. They remain **two separate scene contracts**: the archetype lives in `scenes/archetypes/<name>/main.tscn`; the native quest binds to the generated main-world room graph and EventBus. Neither is silently substituted for the other. JSON blueprint export omits both opt-ins without erasing the user's saved choices. The historical request contract remains byte-compatible when features are not opted in.

A second opt-in exposes the already existing headless Godot **main-world** boot through `playtest='auto'|'require'`. To prevent falsely treating world boot as proof of an executable sidecar, `playtest_archetype_scene()` was added: it independently imports a disposable project, boots `res://scenes/archetypes/<name>/main.tscn` with a bounded frame/time budget, requires Godot exit zero and the exact `ARCHETYPE_LOOP_COMPLETE <name>` marker, rejects error/failure markers and timeouts, and deletes the temporary project. No engine is downloaded and no shell command is constructed.

- **Off (default):** no native dynamic checks; preserve all previous build behavior.
- **Best effort:** check world and opted-in sidecar when Godot is locally installed; return `unavailable` when it is not, without falsely marking it passed.
- **Require:** refuse project publication when main-world boot fails, the Godot binary is missing, or the selected playable sidecar fails to complete. A JSON target cannot request native playtesting.

The Forge run panel displays separate evidence for main-world Godot boot and independent playable-scene completion, plus the selected playable template and native-quest sealed-source receipt. A result is only shown as passed when both `status='passed'` **and** `passed=true` agree. Absence of a sidecar qualification is explicitly displayed as *not dynamically tested*. Source-level and hermetic qualification includes `skeleton/testing/test_gameforge_playable_quest_convergence.py`, `test_gameforge_archetype_playtest.py`, and `frontend/scripts/skeleton-forge/playable-scene-evidence.test.cjs`; real engine and installed-device proof is still an independent hold, and synthetic mock passes never substitute for it.

## Live catalog robustness and questionnaire progress

`frontend/src/features/GalaxyStudioFactory/genreRegistry.ts` validates and bounds optional live Galaxy genre records while preserving all **69** historic offline fallback entries, even when the server returns a partial or stale list. Live-only selected genres can be restored after the validated catalog arrives; explicit user selections always outrank delayed restoration. `galaxy-genre-registry.test.cjs` locks this in against malformed IDs, duplicate entries, unbounded subgenres and reordered fallbacks.

The cross-editor handoff also preserves the original GameForge questionnaire **step** rather than restarting at the brief. A malformed/unreachable target step is reset safely to Vision. Playable-scene choice, Godot qualification mode, original native quest settings, design beats, axes, and applicable era/genre options are retained across editor visits.

**Release status:** source and regression additions are committed to a review-only PR, with exact-head CI not yet verified. An E2E Godot engine boot, platform installer, and real on-device interactive playthrough are outstanding, not assumed green.

**Godot binary provenance is reported separately from runtime behavior.** A world or sidecar can complete successfully on an existing local `godot4`/environment binary while `verified=false` because it was not admitted by the artifact-plane SHA-256 manifest. The run panel now displays this condition as a warning for each successful but unverified binary; no such result is promoted into release-grade installation evidence. Only independent exact-head source, admitted-binary, and installed-device qualifications can close that hold.

## In-game playable archetype gateway

The sidecar playable archetype no longer requires users to browse `res://scenes/archetypes/<archetype>/main.tscn` manually in the Godot editor. Opt-in Godot builds now include a **native, in-world Play <Archetype> prototype control** created by `PlayablePortal`, and a **Return to Forge world** control when inside the sidecar. The main scene remains `res://scenes/levels/run_level.tscn`; only explicit playable opt-in adds `scripts/autoloads/playable_portal.gd` and the matching autoload registration. Source uses a hardcoded admitted archetype ID, rejects conflicting autoloads or missing scenes, does not invoke arbitrary commands or remote services, is inert during headless CI, and keeps navigation fail-closed.

This is a **separate gameplay path**, not an assertion that the native quest and archetype loop have been fused into one quest graph. Both the room-entry quest and in-game archetype gateway may be generated in the same Godot project. The final emission stage independently revalidates **both** attached sources after composition and before the manifest/verification and disk publication; the response carries the portal source SHA-256 and a `sealed` indication conditioned on successful full-pipeline source evidence. The GameForge run panel reports whether launch/return wiring is source-sealed, separately from runtime Godot completion.

`skeleton/testing/test_gameforge_playable_portal.py` and the original `test_archetype_playable_e2e.py` now qualify the emitted GDScript autoload, world-to-prototype and return labels, binding to all three supported archetypes, source tampering rejection, native quest coexistence, headless inert behavior, and no change for builds without the opt-in. `playable-scene-evidence.test.cjs` distinguishes a source-sealed gateway from an unsealed one. This remains code and static test coverage, **not proof of user taps or scene transitions on an installed physical device**.

## Portable, source-verified Godot project export

GameForge's existing `/api/skeleton/run` route always removed the complete generated file bodies for its normal frontend calls, and the UI exposed no way to obtain the game. The export now has a separate explicit questionnaire choice: **Prepare Godot ZIP**. The choice is carried through Forge ↔ Galaxy handoffs; all non-opted-in builds retain their original lightweight response shape.

When explicitly selected, the same synchronous forge run asks for `include_files: true`. The server refuses to return file bodies unless the build succeeded, the source manifest is present, the target is Godot, the file count is at most **256**, and total UTF-8 source is at most **8 MiB**. If any source export condition fails, the game run result stays available while the source bodies are excluded and the export status is `unavailable`. These limits prevent accidental transfer of an unbounded generated project to a phone.

On success, GameForge's Run panel shows **Save or share Godot ZIP**. It packages the **exact file bodies returned by that successful run**, without performing a second generation or remote upload. `sourceArchive.ts` implements a deterministic, ordinary ZIP archive with stored entries, CRC-32, central-directory records, strict paths, a 256-file budget, an 8 MiB source budget and a 9 MiB package budget. It requires `project.godot`, a matching inventory, and an original source-manifest digest. `shareSourceArchive.ts` independently checks every file's SHA-256 **and** the canonical manifest SHA-256 using `expo-crypto` before writing or sharing. User/account changes during the asynchronous operation abort publication.

On Android/iOS the generated ZIP is written to app cache through Expo SDK 55's `File` / `Paths` API and passed to the system-native `expo-sharing` sheet for a user-chosen save or transfer. On web it uses a user-initiated Blob download. The application does not upload these project files to a cloud provider. The archive is a **Godot source project**, not a compiled, signed, independent executable, and requires a compatible Godot editor/runtime for desktop build/export.

New hermetic coverage: `skeleton/testing/test_gameforge_source_archive.py` exercises the bounded API, no-export defaults, denied JSON/failed/unsealed exports and oversize source rejection. `frontend/scripts/skeleton-forge/source-archive.test.cjs` parses local and central ZIP records, verifies byte-for-byte project roundtrips and deterministic ordering, and checks traversal, bogus manifest, mismatched inventory, 256-file and 8 MiB limits. Both suites are in the exact-head qualification workflow. Actual mobile share-sheet and Windows Godot import remain independent device/first-install release holds.
