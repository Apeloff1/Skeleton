# Source-pinned original homebrew/runtime recovery

**Reconciliation date:** 2026-10-13\
**Baseline:** current `main`, not the historical branch tree\
**Custody:** `Apeloff1/Skeleton` PR #3593 at `7f9be557bac3a4108dfc683716b15437de30f547`\
**Recovery branch:** `feat/original-homebrew-core-recover-20261013`

## Exact scope

Recovered the independent source-pinned CHIP-8 machine, deterministic
gameplay capabilities, portable C89 exporter, platform capability catalog,
rights/admission checks, playable project capsules, homebrew editing, platform
porting and native previews. Also recovered the companion CLI modules in
`scripts/game/`, 11 source-pinned functional and negative tests, and
standalone historical rights/export/porting documentation.

Unlike a broad historical squash, this recovery adds only missing files.
It does **not** restore older copies of the installer, frontend, `local_ai.py`,
AI model-runtime packages, provider routes, or GitHub workflows over newer
current-main implementations.

## Supported boundaries

- CHIP-8 is an original-code interpreter/export target, not an emulator for
  unrestricted commercial ROMs.
- User inputs and generated content require explicit game rights/provenance
  review; original-game support is not authorization to ship third-party
  copyrighted assets.
- A portable C89 source export is not a claim of testing on every original
  computer/console or compliance with physical hardware and SDK requirements.
- The offline preview modules are callable Python components, not a completed
  desktop UI/installer or proven hardware deployment.
- The old `skeleton.app.offline_cli` is intentionally **not** imported: its
  original `OfflineGGUFSession` interface no longer matches the modern
  canonical local AI runtime on `main`.

## Acceptance and evidence

The restored tests cover deterministic replay, metadata/rights refusal,
CHIP-8 execution and export, portable C89 code generation, capability graph,
playability, game project capsules, homebrew editing and porting, and preview.
Run the relevant tests and full CI against the **exact** PR head before
calling this a qualified release. The historical source is provenance for the
implementation, not an independent verification of this integration.
