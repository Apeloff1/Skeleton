# Source-bound Expedition Ledger — original playable campaign

This source package provides 49 original self-contained tactical exploration chapters
across seven biomes and seven professions. Each playable chapter includes a grid
layout, typed narrative quest, bounded encounter effects, unique design record,
and its own tests. The shared engine provides deterministic tile transitions,
key/objective/exit gates, per-tile one-shot rewards, resource exhaustion,
branch encounters, shortest-route planning, canonical replay/save/restore,
and state-integrity receipts.

The published catalog is a strict allowlist. No remote models, outside assets,
third-party games, network calls, or dynamic plugin execution are needed.

## Run

```bash
python -m skeleton.game.expedition_ledger.cli --episode ashen_delta__cartographer --plan
python -m skeleton.game.expedition_ledger.cli --episode copper_tundra__navigator --moves east,east,east
python -m pytest tests/game_expeditions -q
```

A save digest is unkeyed SHA-256 of canonical evidence, **not** a signature or
security attestation. Restore additionally replays the bounded command history
against the exact published chapter digest and rejects impossible states.
Chapter JSON is trusted installed application source, **not** an importer
for hostile archive packages. Untrusted imports remain in the separate
descriptor-anchored asset-ingest security boundary.

## Play contract

- S starts, K unlocks O, O unlocks E (win).
- H and X cause bounded harm; R/C restore energy; M heals.
- F and ? influence reputation; L supplies optional lore score.
- Every command consumes energy and counts against the turn budget.
- The exit never wins without the objective; death/exhaustion is terminal.
- The engine is headless/offline text gameplay, not a Godot/device certification.
- The authored side content and multiple routes are optional; the audited
  shortest route is source-derived rather than hardcoded into the engine.

## Evidence and exclusions

Every state and receipt binds to the local original chapter layout, quest and
encounter digest. Replay prevents optimistic state rewrites and records all
commands. This alone does not prove AI generation quality, render performance,
consumer installation, licensing of external packages, or release readiness.
