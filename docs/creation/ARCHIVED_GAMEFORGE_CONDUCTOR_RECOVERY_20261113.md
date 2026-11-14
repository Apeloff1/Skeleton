# Recovery of the original seven-stage GameForge conductor (#807)

Historical source: `archive/pre-rebase-gameforge-conductor-20261113-8e20778a`,
3 commits ahead and 471 behind modern main as of November 13, 2026.

The archived implementation is restored **source-preserving** as a separate
`skeleton.gameforge` namespace, not overwritten onto the canonical
`skeleton.context.pipeline.GameForgeRun` ten-stage engine. It includes
its seven ordered stages (vision, snowball, prototype, mass_forge, world,
cockpit, export), deterministic genre loops for platformer/puzzle/RPG/
shooter/strategy/racing/adventure/sandbox, four art/hardware eras, a
chained receipt ledger, manifest verification and safety admission.

The existing backend router now exposes `POST /api/skeleton/conductor/preview`
with bounded input. It returns deterministic manifest, receipts and artifact
names/digests, **not raw artifact bytes**, project writes, installs or native
first-install claims. No LLM/provider/network dependency is added.

This is a compatibility/recovery capability for agents and tooling; use the
modern canonical pipeline for main GameForge production and Godot builds.
Cross-engine project schema conversion requires separately versioned adapters,
output provenance, input remapping and functional gameplay validation.

Qualification: `python -m pytest -q skeleton/gameforge/test_gameforge_conductor.py backend/tests/test_historical_gameforge_preview.py`, then whole exact-head merge/security gates.
