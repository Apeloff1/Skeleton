# Skeleton — Surrounding Systems Build Plan

Status legend: ✅ done · 🔨 scaffolded · ⬜ pending
Updated 2026-08-30, anchored to the deep-cut ledger (fe5ec07 → 62b36bf).

## Correction log

- ca9238c mistakenly rewrote api/server.py + api/errors.py; restored (b4790a1).
- B4/B5 deploy constraint: backend image originally vendored only backend/;
  shims guarded; B5 vendored skeleton/ (48963bd).

## Tracks — all DONE

A · B · C · D · F · G · H · H5 · I · Docs · J · K (see prior sections of the
git log for each track's commit chain).

## Track K — Cortex coverage — DONE (c81cfbe, this commit)

- [x] K1–K4. Subsystem smokes: callosum, MoE, REINFORCE, sleep (c81cfbe).
- [x] K5. End-to-end `JeevesCortex.think()` integration: construction with
      local slots, status shape, full trace pipeline, own-system growth
      across turns, recall after ingest, genesis-handle class identity
      (this commit).

## Track E — Cleanup pass (deferred, requires local git ops)

E1–E4 unchanged (root sprawl, SEVEN_BY docs, godot binary, shim removal).

## Remaining ideas

- H5.4: genesis cortex twin vs live singleton, once $SKELETON_OWN persistence
  exists in the container.

## Completed cuts (ledger)

fe5ec07 · c553ef8 · bdca180b · b4790a1 · f6c7a78 · 31c8541 · e3eaeca ·
3ebed65 · 9622493 · 5a4d78a · 972b802 · e6e765b · df7fbcd · a5abbdc ·
3b22c74 · 3892273 · 3033821 · bc4fa6b · 4126b52 · 6fab006 · c81cfbe
