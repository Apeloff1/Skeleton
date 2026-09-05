# CHANGELOG

All notable changes to Skeleton.

---

## 2026-09-05 — Looped decode wiring

- think-gate opens on reasoning tokens. krouter sets loop+family.
- Orchestrator decode runs scaled/smelt. Runtime polish tags loop_r.

---

## 2026-09-05 — Looped transformer burst

- SCSE, shortcut, layer/stack loop, MoDr, R-budget, orbit,
  per-loop KV policy, test-time R schedule.
- Looped poke 19/19. kselect long+loop → smelt.

---

## 2026-09-05 — Looped transformer kernels

- unroll, MoR, SMELT, ETD, PLT, overthink halt, KV-share, RK4, inject, ponder.
- Bank slot looped. Law: R=2 default; R>2 only with halt.
- Version 2026.09.05-looped.

---

## 2026-09-05 — Social kernel wave 2

- treeattn, chunkprefill, ragged, prefixhash, marlin, onlinesm,
  packgqa, persistkv, cascade, megafuse, kselect.
- SocialK poke 20/20. kselect: mobile+long→linattn, spec→tree, embed→ragged.

---

## 2026-09-05 — Social-parsed inference kernels

- linattn, xquant, fp8kv, pagekv, flashdec, specdec/MTP, GQA, sparseattn.
- Bank slot socialk. Cites FlashQLA / XQuant / FlashMLA / specdec.
- Version 2026.09.05-socialk.

---

## 2026-09-05 — Obscure and superfluous kernels

- 20 named ops + bank slot obscure on mobile.
- Version 2026.09.05-obscure.

---

## 2026-09-04 — Policy steering segment begins

- Added persistent operator policy state for quality thresholds and repair toggles.
- Added policy cards and a policy-control card to expose the state cleanly.
- Added `docs/POLICY_STEERING_SEGMENT.md` and updated the build plan to start Track P.
- Version 2026.09.04-policy.

---

## 2026-09-04 — Operator diagnostics command surface

- Added direct diagnostics surfaces for failures, repairs, activity, and recurring issues/targets.
- Added failure/activity/recurring cards and wired them through the command deck and HTTP.
- Updated corrective-control docs and freeze docs to reflect parity across game logic and direct operator diagnostics.
- Version 2026.09.04-diagnostics.
