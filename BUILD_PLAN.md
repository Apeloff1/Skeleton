# Skeleton — Surrounding Systems Build Plan

Status legend: ✅ done · 🔨 scaffolded · ⬜ pending
Updated 2026-08-30, anchored to the deep-cut ledger (fe5ec07 → 62b36bf).

## Tracks — all DONE

A · B · C · D · F · G · H · H5 · I · J · K · Docs (see git log for chains).

## Track L — Social-media SOTA sweeps (waves 1–4) — DONE

- [x] Wave 1 (90118451): adaptive RRF plane weights, KVFlow-style workflow-
      aware eviction, utility-prioritized sleep replay, SEVEN_BY archive index.
- [x] Wave 2 (78a1bb9e): memory distillation (worth gate + budgeted store),
      bounded self-verification with marginal-gain stop. Speculative decode
      verified already complete (cortex/speculate.py) — not rebuilt.
- [x] Wave 3 (37d4a26, 574ecb5): cascade router (difficulty pre-check +
      confidence escalation + cost accounting), head/tail context compaction
      with compaction markers, five-class failure taxonomy. NON_LEXICAL_WORDS
      extended 12 → ~85 forms with false-positive guards.
- [x] Wave 4 (c792698, this commit): uncertainty gate (confidence ×
      agreement entropy → ANSWER/ABSTAIN/ESCALATE), structured-output
      contracts (validate → repair → revalidate), swarm blackboard (typed
      TTL workspace over the bus), recovery executor (taxonomy-driven
      retry/repair/replan with an audit log).
- [x] Tests: test_sota_upgrades.py (10) · test_sota_wave2.py (10) ·
      test_sota_wave3.py (16) · test_sota_wave4.py (16) — 52 SOTA tests,
      109 total in the suite.

## Track E — Cleanup pass (deferred, requires local git ops)

E1–E4 unchanged (root sprawl, SEVEN_BY file moves, godot binary, shim removal).

## Integration seams for the next pass

- `uncertainty.ESCALATE` → `cascade.strong` — the two route together but no
  caller composes them yet; a thin `RoutedGate` wrapper would close it.
- `plane_weights.observe` needs a consumer-feedback endpoint on the
  retrieval route.
- `Contract` can back the OUTPUT repair hook in `recover()` for the
  retrieval/forge routes.

## Completed cuts (ledger)

fe5ec07 · c553ef8 · bdca180b · b4790a1 · f6c7a78 · 31c8541 · e3eaeca ·
3ebed65 · 9622493 · 5a4d78a · 972b802 · e6e765b · df7fbcd · a5abbdc ·
3b22c74 · 3892273 · 3033821 · bc4fa6b · 4126b52 · 6fab006 · c81cfbe ·
3b06f15 · 90118451 · 8776b878 · 78a1bb9e · 37d4a26 · 574ecb5 · c792698
