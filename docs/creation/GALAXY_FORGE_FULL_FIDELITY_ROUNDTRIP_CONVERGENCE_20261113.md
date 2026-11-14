# Source-preserving Galaxy ⇄ GameForge full-design authoring roundtrip

## Exact lineage

- Stacked base: main-target PR #5321 at
  `347acd8f5bca656d58c3b4d1076ec1af4c61a411`.
- Original historical creator work: PR #5313, snapshot
  `b161a83c6719d99da253cd1506690c8e304acc95`.
- The original historic bidirectional creator bridge, editor draft codec,
  account-scoped AsyncStorage custody and Galaxy/Forge route navigation
  were selectively reconciled with the newer cumulative main-target branch.
  The legacy three-mode editor and old standalone native scene source were
  **not** copied over eight-mode runtime or source provenance.

## Completed source functionality

1. The original Galaxy Studio editor can **reopen a full editable saved
   design**: all 14 matrix families and narrative phases, genre fusion,
   100+ advanced sliders, classic sliders, rendering styles, production
   sliders, file-scale target, platform/language targets and descriptive
   design fields. A separate validated full Galaxy build-profile snapshot
   is retained for the Forge API; editable design and compiled build
   profiles remain separately versioned.
2. The historical UI initializer set restores 78 original authored fields
   rather than only saving a limited subset. A deferred offline/live genre
   selector restores known Galaxy specialties and never overrides a user's
   explicit new selection.
3. Explicit Galaxy **Save editable workspace**, exit with save-before-close,
   and **Continue full questionnaire in GameForge** controls preserve
   authored work. Failed storage leaves the Galaxy editor open. No
   background game generation.
4. The route's one-use, bounded, account-scoped custody retains Forge's
   vision, five brief facets, twelve design beats, ten independent
   cockpit axes, current questionnaire step, original genre, eight-mode
   native mini-game selector and launch mode, quest settings, Godot native
   qualification selection and source ZIP export preference.
5. The Galaxy→Forge route combines two complementary transfers:
   - A bounded, verified creator bridge containing shared Forge design and
     an optional validated Galaxy profile, consumed once per owner; and
   - A one-use opaque URL hint that consumes the **current exact 14-matrix**
     authored full Galaxy build profile from in-memory custody.
   No bearer token or authored source body enters the URL.
6. A passive Galaxy close restores the incoming Forge draft without
   applying unsaved Galaxy changes. Explicit Continue saves changes
   first. Previously accepted Forge drafts may be returned after long
   Galaxy editing with a newly minted, short-lived transport envelope.
7. A source-bound **Return to original Studio project** control appears
   only for an accepted Studio-origin revision; its return uses the
   original one-time source identity custody.
8. Original 69 Galaxy specialty choices still map into 158 GameForge
   brief labels, without claiming 69 or 158 native game engines.
   The eight authored native Godot prototypes and their independent
   qualification, local Jeeves, script/input replay, source ZIP, resource
   controls and immutable provenance remain present.

## Security and fidelity boundaries

- One-use handoff expiry: **20 minutes**; no replay within the JS
  runtime and no cross-account draft access. A stored authoring profile is
  bounded by validated **450 KB** profile complexity plus limited
  envelope overhead. Editor draft snapshots use **320 KB** / **30-day**
  bounds and owner-scoped SHA-256 bearer fingerprints; local AsyncStorage
  should **not** be represented as encrypted storage.
- Receiver validates format, step, genre/axis whitelists, quest count,
  native mode identity, finite numbers, profile shape and account epoch;
  malformed or expired data is rejected. Persistent source is never
  handed directly to execution engines as code.
- Source tests cover original 15 Galaxy bridge scenarios, original 5
  full editable Galaxy draft scenarios, all eight GameForge playable
  modes, full 14-matrix profile preservation, wrong-direction reads,
  concurrent one-use consumption, auth switching and storage faults.
- **A source-only CI success is not an independent mobile-device
  acceptance, installed Windows/WSL2 run, or original Godot game
  playthrough.**

## Required exact-final-head qualification

```sh
cd frontend
yarn install --frozen-lockfile --ignore-scripts
node scripts/patch-node-modules.js
node scripts/verify-no-release-npm-security.js
yarn test:skeleton-forge
yarn typecheck
yarn check:expo-native-compat
```

Also require full final-head Merge Readiness, Backend Quality,
App Foundation E2E, Canonical AI-tree parity, native Godot gameplay
on an admitted exact binary, local GGUF Jeeves real inference,
CodeQL, secret/workflow-input/malware scanning, dependency/hygiene/
artifact policy and independent install/recovery/provenance checks.

**REVIEW ONLY. No merge, auto-merge, release or first-install signoff
until required exact-head evidence succeeds.**
