# First-install Studio ⇄ GameForge complete source-bound return

**Parent**: review-only PR #5322 at `e978bde2e3cdb30b1b2157dde70b9764ce21b053`.
**Source**: archived historical PR #5313, head `b161a83c6719d99da253cd1506690c8e304acc95`.

## Why this integration is necessary

GameForge's previous `onReturnToStudio` button published a `studio` creator
handoff and navigated to `/skeleton-studio`, but the installed first-run
Studio screen did not consume that handoff. It also used global unscoped
AsyncStorage keys. Thus the creator roundtrip was not a complete functional
vertical and could cross accounts on a shared device. The missing receiver
has now been integrated; no signoff on device behavior is claimed.

## Source implementation

- Restore the historical live Studio session envelope and source-bound
  project launcher, while preserving all later strict questionnaire and
  modern eight-native-mode validation in the actual model.
- Studio -> advanced Forge takes its original project ID + optimistic source
  revision and publishes a short-lived one-time, owner-scoped handoff.
  The Forge -> Studio receiver consumes only `target=studio` and
  applies an edited questionnaire **only if both ID and revision match**.
- If the original was changed or deleted, edited Forge work is preserved
  as a separately named Studio project. An exact retry of an already-applied
  version is acknowledged without creating another project.
- Each authored Studio edit receives a monotonic revision token (even
  on a same-millisecond edit), so concurrent changes cannot silently
  reuse an ancestor revision.
- Preserve and restore all modern GameForge controls: original Galaxy
  14-matrix profile, 158 creative brief labels, 69 specialty picker,
  ten design axes, eight native playable modes and launch selection,
  quest, source ZIP preference and separate Godot verification mode.
  Saved projects use the **current strict** `normalisePresetState`
  validation; malformed or unknown execution choices hold all saves.
- Create an account-scoped Studio AsyncStorage adapter using SHA-256
  opaque fingerprints and `getAuthEpoch` fencing for three keys:
  onboarding, projects and preferences. Historical unscoped data
  is never auto-assigned to a logged-in creator. A visible, explicit,
  read-only legacy import path retains the originals on conflict.
- Serialize project snapshots per store so out-of-order async device
  writes cannot revert a newer edited project. Preferences and onboarding
  commit before the main authored projects; failures surface and can
  be retried without poisoning the serialized write queue.
- Persist source receipt summaries only, not complete generated `files`,
  source manifest bodies or a claim that the temporary ZIP is still
  available. Changing the design marks a previous successful run outdated
  and sends the user back to edit/rebuild.
- Restore first-install source ZIP share UI only for the actual live
  successful run, preserving source-archive custody and account/epoch checks.
- Restored Studio session is keyed by auth epoch, invalidating cached
  project/UI state after sign-out. The original Forge transfer and Studio
  return use explicit actions; navigation never silently runs a game build.

## Acceptance and holds

Original historical account isolation tests (12 cases) and source ZIP/
legacy UI tests (2 cases) are restored; 7 additional tests qualify the
full eight-mode return, duplicate/replayed handoff, conflict copy,
source ZIP redaction, outdated receipt and invalid input rejection.

Full exact-final-head `yarn test:skeleton-forge`, `yarn typecheck`,
`yarn check:expo-native-compat` and mandatory installed third-party
security verification are required. Also require complete exact-head
Merge Readiness, backend, E2E, CodeQL/malware, dependency/rules,
AI-tree parity, live native Godot/GGUF local Jeeves and independent
Windows/WSL2/device/recovery/provenance evidence.

**Review-only. No merge, release, auto-merge, first-install signoff or
removal of merge holds without the exact-head required gates.**
