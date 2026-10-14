# Dependency board — Skeleton FULL APP COMPLETION

Snapshot: **2026-10-10** against `main` @ `79fe3870e331563f5da85471976f53aaf10c240d`.
Open PR count at snapshot: **14** (#3593–#3607). Re-list before acting; this file ages fast.

Historical note: PR **#25** (GameForge cortex / EchoBackend) **merged** 2026-09-12. Issue **#127** (required checks / merge-readiness) is **closed**; enforcement of **Merge Readiness** on `main` remains an admin follow-up for Grenn.

## Critical path (rollout)

1. **Wave 0 — stacked bases** — land `#3601` and verify, then retarget/merge `#3603` (stacked on `fix/dragon-ci-reliability-20261009`).
2. **Wave 1 — merge gate reality** — Grenn applies `scripts/configure_main_protection.sh --apply` so **Merge Readiness** is required on `main`. Until then, green Checks are advisory, not authorization.
3. **Wave 2 — focused craft on `main`** — merge green, non-draft, non-stacked PRs that do not fight Wave 0/1: `#3606` (combat design, additive), `#3607` (animation pipeline; BB via Grok Bot authorized merge once CI green).
4. **Wave 3 — large product packs** — `#3604` (game builder / rights / native formats) only after exact-head native + Merge Readiness evidence; `#3602`/`#3595`/`#3597`/`#3593` offline/AI serving only when their own gates are green and do not regress Wave 0.
5. **Wave 4 — drafts / wide Dragon** — `#3605` and other drafts stay parked until ready-for-review **and** Merge Readiness green; do not treat local Dragon suite green as rollout.

## Waves

### Wave 0 — Stacked / must-land-first

| PR | Draft | Head → base | Area | Notes |
| --- | --- | --- | --- | --- |
| [#3601](https://github.com/Apeloff1/Skeleton/pull/3601) | no | `fix/dragon-ci-reliability-20261009` → `main` | Dragon CI / ROM / Windows native | **Upstream of #3603**. Merge and verify before retargeting #3603. |
| [#3603](https://github.com/Apeloff1/Skeleton/pull/3603) | no | `feat/dragon-all-era-platform-coverage-20261009` → **`fix/dragon-ci-reliability-20261009`** | Dragon platforms (169 / 92 source) | **Stacked.** Body: merge #3601 first, then retarget onto `main`. Source % ≠ gameplay completion; 0 hardware-verified claimed. |

### Wave 1 — Gate / protection (ops, not a product PR)

| Item | Owner | Notes |
| --- | --- | --- |
| Require **Merge Readiness** on `main` | Grenn | `scripts/configure_main_protection.sh --apply` / `--verify`. Policy already documented in #127 / `docs/CI_REQUIRED_CHECKS.md`. |
| Do not weaken fail-closed lanes | Production + Grenn | Quarantine Policy, Unit, Integration Smoke, Lint Type Security, PR Automation Tests |

### Wave 2 — Focused craft (prefer early merge when green)

| PR | Draft | Head → base | Area | Notes |
| --- | --- | --- | --- | --- |
| [#3606](https://github.com/Apeloff1/Skeleton/pull/3606) | no | `snappo/combat-design-model` → `main` | Combat design | Additive `combat_design/`; own focused workflow. Low coupling. |
| [#3607](https://github.com/Apeloff1/Skeleton/pull/3607) | no | `yosh/anim-pipeline-hardening` → `main` | Animation | `hit_frame` timing; BB via Grok Bot: merge when CI green. |

### Wave 3 — Large product / AI / offline

| PR | Draft | Head → base | Area | Notes |
| --- | --- | --- | --- | --- |
| [#3604](https://github.com/Apeloff1/Skeleton/pull/3604) | no | `feat/game-builder-legacy-platform-porting-20261009` → `main` | Game builder / rights / native binaries | Author: do not merge until exact-head native matrix + required CI pass. |
| [#3602](https://github.com/Apeloff1/Skeleton/pull/3602) | no | `fix/ai` stdlib-only model-runtime | AI runtime imports | Reliability fix; confirm no overlap with offline app PRs. |
| [#3595](https://github.com/Apeloff1/Skeleton/pull/3595) | no | native serving cleanup | AI serving | Evidence-bound completion status. |
| [#3597](https://github.com/Apeloff1/Skeleton/pull/3597) | no | offline native/GGUF chat | Offline AI | Coordinate with #3593 console. |
| [#3593](https://github.com/Apeloff1/Skeleton/pull/3593) | no | standalone AI console | Offline / app | Durable local chat. |
| [#3600](https://github.com/Apeloff1/Skeleton/pull/3600) | no | transformer atomic weights/KV | AI / transformer | Security-sensitive; keep fail-closed. |

### Wave 4 — Drafts / wide surface (park)

| PR | Draft | Head → base | Area | Notes |
| --- | --- | --- | --- | --- |
| [#3605](https://github.com/Apeloff1/Skeleton/pull/3605) | **yes** | `feat/dragon-wisdom-review-20261010` → `main` | Dragon wisdom / companion | Explicit non-claims (legal, hardware, training). Hosted checks pending at snapshot. |
| [#3599](https://github.com/Apeloff1/Skeleton/pull/3599) | **yes** | offline multi-document | AI curation | Draft. |
| [#3598](https://github.com/Apeloff1/Skeleton/pull/3598) | **yes** | standalone native app / learning | AI app | Draft. |
| [#3596](https://github.com/Apeloff1/Skeleton/pull/3596) | **yes** | offline conversation recovery | AI | Draft. |
| [#3594](https://github.com/Apeloff1/Skeleton/pull/3594) | no | docs/index masterplan | Docs | Low risk; merge anytime green. |

## Overlaps to watch

- **Dragon stack:** `#3601` → `#3603`; do not merge `#3603` onto `main` while base is still the reliability branch.
- **Offline / AI app cluster:** `#3593`, `#3597`, `#3598` (draft), `#3596` (draft), `#3599` (draft) — pick one primary app PR; close or rebase duplicates after review.
- **Game builder vs Dragon platforms:** `#3604` and `#3603` both touch historical native / platform surface — sequence and rebase; do not double-claim platform counts.
- **Combat / animation:** `#3606` / `#3607` are additive; still watch shared `simulation/` and frontend animation paths for conflicts with Dragon visual play (`#3605`).

## Out of critical path until proven

Anything that claims hardware-verified platforms, legal non-infringement, consumer Windows/macOS release, or automatic legal interpretation without Merge Readiness + admin-enforced protection.
