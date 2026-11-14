# GameForge design preset recovery — local creative workspace

Date: 2026-11-13
Integration: historical creator convergence PR #5316.

## Problem being solved

The historical Galaxy questionnaire, 14 matrices, ten-axis cockpit,
quest selection and eight playable loops now coexist in the modern Forge.
Without a named preset library, moving to another project or reopening the
creator causes settings to be lost or difficult to reproduce.

## Implemented workflow

The existing five-step questionnaire's Forge Options screen now exposes
**Save / load game designs**. A user must explicitly enter a name and
select **Save current design**. Presets survive reopening the app on the
same device using the existing AsyncStorage library.

Each named preset stores the validated creative-brief answers, design-beat
answers, vision text, sparse ten-axis instrument values, specialized genre
selection, the full fourteen-matrix Galaxy Studio source profile, explicit
quest mode/length, original playable mode, startup/bonus scene choice,
Godot or JSON target, configured era and generation. Restoring selects the
Forge Options step for human review before any generation. Nothing is sent
to a remote provider or started automatically.

A name matching an existing design (case-insensitive) intentionally
updates it rather than creating a duplicate. Deletion requires a second
**Confirm deletion** action. File/user/source configuration is unaffected
until the user selects a loaded preset and chooses to forge.

## Privacy and scope

These are **local convenience presets, not authenticated server projects,
encrypted records, digital signatures or provider credentials**. The
interface warns against putting secrets into a design. No record is
created until the user explicitly saves. The original Galaxy one-use
handoff stays in memory unless the author chooses to save its content.
Never represent client storage as a protected cloud project vault.

Only supported questionnaire fields are serialized; arbitrary keys,
access tokens, run responses, runtime secrets and hidden assistant data
are excluded from the saved structure.

## Bounded source replay

- Version: skeleton.gameforge.design_presets.v1
- Explicit storage key: @skeleton_gameforge_design_presets_v1
- Up to 24 named presets, each at most 475,000 JSON characters
- Entire store limited to 2,000,000 JSON characters
- Preset names 1–64 printable characters; no silent eviction
- Original 4,000-character vision maximum
- Only recognized brief choices, bounded Beat identifiers and answers
- Ten authoritative source-design axes, all finite and within [0,1]
- Exact original 67-genre catalog validation; 14-matrix profile must pass
  the existing Galaxy schema and complexity budgets
- Quest steps 1–8; playable modes restricted to the exact authored registry;
  one and only one launch scene; no ambiguous quest/mini-game main scene
- Strict versioned JSON decode, duplicate rejection and no resetting or
  overwriting existing storage when it is damaged or unsupported
- Restored state reconstructs a fresh RunRequest through the original
  GameForge pipeline; default requests remain unchanged

## Verification

The new front-end test suite
frontend/scripts/skeleton-forge/design-presets.test.cjs
exercises complete authoring roundtrip, original source matrix fidelity,
deduplication, storage budgets, injected fields, malformed state,
unsupported modes, safe failure and SSR visibility.

The existing protected Merge Readiness gate runs the entire
yarn --cwd frontend test:skeleton-forge suite on the exact PR head.
This is a source contract; native Android/iOS storage persistence and
physical device controls require independent device qualification.

No merge or release is authorized by this document.
