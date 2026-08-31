# Skeleton — Surrounding Systems Build Plan

Status legend: ✅ done · 🔨 scaffolded · ⬜ pending
Updated 2026-08-31, anchored to the deep-cut ledger (fe5ec07 → 62b36bf).

## Tracks — all DONE

A · B · C · D · F · G · H · H5 · I · J · K · Docs (see git log for chains).

## Track L — Social-media SOTA sweeps — DONE (waves 1–4 + routed gate)

## Track M — Bi-directional frontier catch-up — DONE (af7d0a6, this commit)

Direction A (frontier → production, adopted now):
- [x] M1. A2A task envelopes — `swarm/handoff.py`: typed envelopes with a
      SUBMITTED→WORKING→COMPLETED|FAILED|CANCELLED state machine over the
      kernel bus; every transition an event (A2A hit 150+ orgs / enterprise
      production in year one).
- [x] M2. Verifier rubric — `intelligence/verifier.py`: rule-based
      syntax/structure/safety/size/grounding scoring for generated code,
      with a `VerificationLoop` adapter for revise-until-green.
- [x] M3. Bounded self-improvement — `intelligence/improve_loop.py`:
      generate→verify→keep-if-better with budget, patience, target, and
      min-gain stops plus a full iteration audit trail (AlphaEvolve pattern
      minus the metric-gaming failure mode).

Direction B (production → frontier, discovered this summer):
- [x] M4. Context rot guard — `memory/rot_guard.py`: scores composed
      prompts for attention dilution (length over budget), constraint
      burial (critical rules stuck in the dead zone), and repetition decay
      (stated-once constraints effectively dropped). Verdicts:
      fresh / watch / rot. Composes with `memory/compaction.py`.
- [x] M5. `test_deep_pass.py` — 15 tests over all four modules.

## Track E — Cleanup pass (deferred, requires local git ops)

E1–E4 unchanged (root sprawl, SEVEN_BY file moves, godot binary, shim removal).

## Integration seams for the next pass

- `rot_guard.assess` → `memory/compaction.ContextCompactor` trigger:
  compact when verdict == "rot". Both exist; one wrapper closes it.
- `handoff.HandoffRegistry` → `agents/mesh.py` routing: submit envelopes
  where the mesh picks the assignee by capability.
- `verifier.verdict` → `VerificationLoop.run` for the forge pipeline —
  revise-until-green before materialise.

## Completed cuts (ledger)

fe5ec07 · c553ef8 · bdca180b · b4790a1 · f6c7a78 · 31c8541 · e3eaeca ·
3ebed65 · 9622493 · 5a4d78a · 972b802 · e6e765b · df7fbcd · a5abbdc ·
3b22c74 · 3892273 · 3033821 · bc4fa6b · 4126b52 · 6fab006 · c81cfbe ·
3b06f15 · 90118451 · 8776b878 · 78a1bb9e · 37d4a26 · 574ecb5 · c792698 ·
9c2288d6 · 155010cf · af7d0a6
