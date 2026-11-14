# First-install Studio → GameForge → Galaxy → Studio custody integration (2026-11-13)

## Historical source and staged parentage

- Base: source-preserving GameForge/Galaxy candidate #5322, exact parent
  `21ecc2512b4eef3ba0825758db8fef56fee5b853`.
- Recovered historical source: #5313, source snapshot
  `b161a83c6719d99da253cd1506690c8e304acc95`.
- The historical Studio shell, first-install session controller, build receipt
  panel, owner-scoped AsyncStorage adapter, ordered project writer, and
  historical regressions were reconciled against the current 158-genre,
  eight-playable-mode, local Jeeves, source-bound Galaxy and GameForge code.
- The newer full 14-matrix Studio questionnaire hydrator and its strict
  preset validation remain authoritative; an obsolete three-mode reducer
  was not imported over it.

## Operational user journey

1. On first install, account changes remount the entire Studio session;
   old-run console results, source artifacts, editor contents and ongoing
   build owners do not remain visible across principals.
2. Owner-scoped local storage derives a SHA-256 namespace from the active
   locally held bearer token without putting bearer bytes in storage keys.
   A separate anonymous namespace is retained. All three first-install
   record keys (onboarded, projects, settings) join the existing Galaxy,
   Forge and source snapshot allowlist.
3. Historical unscoped Studio projects remain untouched, read-only and
   unavailable until **explicit user-authorized import**. Duplicate or
   malformed project IDs fail closed; an imported ID never overwrites a
   currently owned project.
4. The first-install Studio user can open an existing authored project
   in the advanced Forge cockpit. A bounded, owner-scoped, one-use return
   envelope records the original project ID and the exact original
   `updatedAt` revision.
5. Forge and optional Galaxy preserve the full questionnaire and eight
   playable-mode settings, 14 original matrices, ten independent axes,
   designer beats, portable source controls, selected target and quest
   options. Neither navigation nor source transfer starts a build.
6. Explicit Forge return to Studio requires that exact source identity
   and original revision. Valid matching source is updated; concurrent
   edits or deleted originals get a separate copy with a distinct ID.
   No merge of conflicting authoring state or partial overwrite.
7. Per-store writes serialize in submission order. The main project
   snapshot is published **last** after prefs/onboarding writes. A failed
   earlier write does not poison the future retry queue, while a real
   storage error is propagated instead of inventing success.
8. Generated Godot source bodies and live-run source manifests never
   enter persisted Studio project records. Only metadata receipts remain.
   Previously prepared source ZIPs are explicitly marked unavailable
   outside the original account-bound live run; a second request never
   silently replaces the original build.

## Tests and qualification

- Recovered historical account-scope and one-use return tests (12 cases),
  plus original Studio model tests and eleven additional original
  reconciliation/storage/metadata regressions, plus four current
  full eight-mode and 14-matrix preservation regressions.
- Enforced via `yarn test:skeleton-forge`, `yarn typecheck`,
  `yarn check:expo-native-compat`, explicit security postcondition checks,
  exact product-surface/AI-tree validation and all other primary CI.
- Source tests do not prove any physical mobile install, real native
  Godot playthrough, Windows/WSL2 or GGUF inference acceptance.
- Preserve `do-not-merge` and independent release/security/device
  holds until final SHA-scoped evidence passes.

## Recoverability limits

Local AsyncStorage drafts are **not encrypted at rest** by this layer and
account identity derives from a bearer fingerprint: a token rotation can
place the user into a distinct namespace unless the app separately
implements a verified, user-approved migration. No cross-account
automatic migration or background synchronization is claimed.

**Review-only. Main untouched.**
