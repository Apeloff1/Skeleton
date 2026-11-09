# Full repository mining manifest

Skeleton is the only destination. Sibling repositories are mines, not products.
Every non-empty repository is inspected for unique algorithms, runtime contracts,
quality gates, assets, protocols, or UX primitives. Empty repositories are recorded
for provenance and skipped. Byte-identical duplicates are never copied wholesale.

## Canonical destination

- `Skeleton` — canonical application and only integration target.

## High-priority active mines

- `gameforge-rs` — Rust core/runtime/governance, FFI, multi-language clients, gameforge cognition/economy/governance primitives.
- `gameforge-middleware` — Zaibatsu gate, principal auth, middleware policy and WORM audit semantics.
- `hyperforge-cockpit-sota` — cockpit UX, browser quality gates, auth invariants, PWA/browser runtime tooling.
- `Tutolage` — historical full-stack ancestor; re-diff continuously for unique post-fork changes.
- `Prood` — large monolith/ancestor; mine only unique post-fork logic and assets.
- `Interesting-22`, `Asds`, `Ggg`, `New-tey` — large private dumps; inspect structurally before accepting the historical "not GameForge" verdict.

## Legacy gameplay lineage — mine mechanics, discard obsolete shells

- `2d`, `2dv1`, `2dv0.2`, `2dv0.3`, `2dv0.4`
- `Openworld`, `Openworld2`, `Openworld3`, `Openworld4`, `Openw3orld4`
- `Newmove`, `Newmove2`, `Newfix`
- `Newsay`, `Newsay2`, `Newsay3`, `Newsay4`
- `Newstuff`, `Newstuff2`
- `Lore-buff`, `Lorebuff`, `Lorebuf22f`, `Lorebuffa`
- `Saymore5`, `Saymore6`, `Saymore7`, `Saymore8`
- `Expa`

Promotion rule: extract simulation, movement, camera, world, entity, dialogue,
procedural, rendering, persistence, input, and content-generation logic only when
it is measurably distinct from Skeleton. Generated caches, obsolete package shells,
and duplicate assets do not survive.

## Empty / provenance-only repositories

At current GitHub metadata these contain no code to mine and remain ledger entries:

- `Nextstep`, `Nextstepz`, `utolage`, `tolage`, `Restorepoint`, `Summer`, `lage`,
  `Hotday`, `Hotdayz`, `Piper`, `Ai-gamestudio`, `Ieresting-22`, `resting-22`, `Prod`.

If any becomes non-empty later it automatically returns to the mining queue.

## Promotion status

### Promoted

- Zaibatsu WORM audit -> `backend/core/worm_audit.py`
- Hyperforge UI regression oracle -> `frontend/scripts/ui-regression-verdict.mjs`
- Rust execution-governance charter model -> `backend/core/charter_policy.py`
- Canonical product boundary -> `backend/core/product_kernel.py`
- Canonical frontend capability vocabulary -> `frontend/src/product/productCatalog.ts`

### In progress

- Rust admission / cancellation / backpressure / request-budget primitives.
- Rust FFI/client contract mining for a stable external automation SDK.
- Hyperforge cockpit state machine and browser-runtime invariants.
- Legacy gameplay lineage differential mining.
- Large private dump structural census.

## Redesign target

The accumulated module graph is not the product UI. The rebuilt app exposes four
stable pillars:

1. **Create** — Studio + World Forge.
2. **Play** — playable builds and live iteration.
3. **Learn** — Jeeves + Academy.
4. **Operate** — runtime, swarm, deployment, observability, governance and audit.

All legacy and mined systems must map behind one of these product contracts or be
kept internal. New features cannot add another top-level product concept without
an explicit product-kernel change and tests.
