# Repository Consolidation Matrix

This is the initial promotion map. It is deliberately conservative: repository names are not treated as evidence that an implementation is superior. Each family must be inspected and characterized before promotion.

| Repository family | Primary role | Initial disposition | Target |
|---|---|---|---|
| Skeleton | AI runtime/orchestration | CANONICAL | `core/`, `ai/`, `services/` |
| Prood | Tutolage/learning platform | PROMOTE | `learning/`, `apps/`, `services/` |
| Tutolage | CodeDock/Tutolage learning + Jeeves | PROMOTE | `learning/`, `ai/`, `apps/` |
| Interesting-22 / Ieresting-22 | Tutolage variants | CHARACTERIZE | best unique modules only |
| Lore-buff / Lorebuff / Lorebuf22f / Lorebuffa | game domain/world/NPC | PROMOTE | `game/`, `domain-packs/lorebuffa/` |
| Openworld / Openworld2 / Openworld3 / Openworld4 / Openw3orld4 | world/simulation iterations | CHARACTERIZE | `game/world/` |
| gameforge-rs | Rust game forge | PROMOTE | `packages/rust/gameforge/` |
| gameforge-middleware | forge middleware | PROMOTE | `services/gameforge/` |
| hyperforge-cockpit-sota | cockpit/web UI | PROMOTE | `cockpit/web/` |
| Ai-gamestudio | game studio UX/product | CHARACTERIZE | `apps/studio/` |
| Newsay / Newsay2 / Newsay3 / Newsay4 | dialogue/language iterations | CHARACTERIZE | `game/dialogue/`, `ai/` |
| Saymore5–8 | dialogue/language iterations | CHARACTERIZE | `game/dialogue/`, `ai/` |
| 2d / 2dv0.2 / 2dv0.3 / 2dv0.4 / 2dv1 | 2D experiments | CHARACTERIZE | `game/2d/` |
| Newmove / Newmove2 / Newfix | feature evolution | CHARACTERIZE | winning implementations only |
| Newstuff / Newstuff2 / Expa | experiments | QUARANTINE | `experiments/` |
| Nextstep / Nextstepz / Newstep | planning experiments | QUARANTINE | `experiments/planning/` |
| Piper | experimental subsystem | QUARANTINE | `experiments/piper/` |
| Restorepoint | recovery/state | INSPECT | `core/runtime/`, `services/backup/` |
| Prod / New-tey / Ggg / Asds | variant/experimental | INSPECT | promotion based on code evidence |
| Summer / lage / Hotday / Hotdayz | empty/experimental shells | ARCHIVE | lineage only |
| utolage / tolage | empty shells | ARCHIVE | lineage only |
| resting-22 | variant shell | INSPECT | lineage only unless unique code found |

## Rules

- `PROMOTE` means actively inspect and integrate useful code.
- `CHARACTERIZE` means compare implementations before selecting a winner.
- `QUARANTINE` means keep source lineage but prevent architectural coupling.
- `INSPECT` means repository name alone is insufficient to decide.
- `ARCHIVE` means preserve provenance but do not spend core engineering effort unless later evidence changes the decision.

## Immediate highest-value sources

1. Skeleton — existing architecture and control plane.
2. Prood — large Tutolage implementation surface.
3. Tutolage — alternate learning/Jeeves implementation with explicit subsystem contracts.
4. Lorebuffa family — domain/game implementation.
5. gameforge-rs + gameforge-middleware — forge execution path.
6. hyperforge-cockpit-sota — cockpit frontend.
7. Openworld family — world/simulation candidates.
8. Newsay/Saymore family — dialogue candidates.

## Safety boundary

No source repository is modified or deleted by this matrix. Consolidation happens on the `frontier/consolidation-foundation` branch until validation is complete.
