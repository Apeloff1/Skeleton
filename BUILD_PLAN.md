# Skeleton — Surrounding Systems Build Plan

Status legend: ✅ done · 🔨 scaffolded · ⬜ pending
Updated 2026-08-30, anchored to the deep-cut ledger (fe5ec07 → 62b36bf).

## Correction log

- ca9238c mistakenly rewrote api/server.py + api/errors.py; restored (b4790a1).
- B4/B5 deploy constraint: backend image originally vendored only backend/;
  shims guarded; B5 vendored skeleton/ (48963bd).

## Tracks — all DONE

A · B · C · D · F · G · H · H5 · I · Docs · J (see prior sections of the git
log for each track's commit chain).

## Track K — Cortex subsystem smokes — DONE (this commit)

- [x] K1. Callosum: fuse stream shapes, Hebb coupling-energy movement,
      snapshot roundtrip (the learned coupling matrix survives), multi-token
      seq fusion.
- [x] K2. MoE: softmax gates sum to 1, acquire stamping, predict-* correctly
      returns None below MIN_FITTED, fingerprint is stable per seed and
      moves when the bank learns.
- [x] K3. REINFORCE: positive advantage steps toward the action, negative
      stays, EMA baseline converges, snapshot roundtrip.
- [x] K4. Sleep: co-fire Hebbian tags, empty-buffer consolidate no-op,
      confidence-based prune, snapshot roundtrip.
- [x] K5. All four read as genuinely implemented, no defects — the gap was
      coverage, not correctness.

## Track E — Cleanup pass (deferred, requires local git ops)

E1–E4 unchanged (root sprawl, SEVEN_BY docs, godot binary, shim removal).

## Remaining ideas

- H5.4: genesis cortex twin vs live singleton, once $SKELETON_OWN persistence
  exists in the container.
- End-to-end cortex think() smoke under a live JeevesCortex (heavier —
  pulls the transformer stack; worth one integration test).

## Completed cuts (ledger)

fe5ec07 · c553ef8 · bdca180b · b4790a1 · f6c7a78 · 31c8541 · e3eaeca ·
3ebed65 · 9622493 · 5a4d78a · 972b802 · e6e765b · df7fbcd · a5abbdc ·
3b22c74 · 3892273 · 3033821 · bc4fa6b · 4126b52 · 6fab006
