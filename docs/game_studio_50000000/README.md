# Forge Studio · 50,000,000 game-authoring workflows

This revision adds **45,000,000 executable worldline compositions** to the previous 5,000,000 source tools and production recipes. They are distinct combinations of real tile edits, typed RPG environmental event pages and (where newly authored) actor/quest adjustments—not 45 million independent engines or finished games.

## New production axes

The ten new worldlines are river_network, city_circulation, wilderness_ecology, tactical_encounters, subterranean_routes, sky_navigation, social_reputation, environmental_pressure, narrative_consequence and cinematic_blocking. The code owner is `skeleton/forge/game_frontier_studio_worldline_production.py`.

Each composes with the existing ten domains, fifty authored archetypes, nine treatments, ten game systems, ten directors and ten final passes. The catalog is indexed virtually, without allocating 50 million command strings, and the same authenticated editor and Godot compiler consume its typed source changes.

## Tenfold documentation

There are **1,000 previously committed technical manuals** in [the previous collection](../game_studio_5000000/README.md) and **9,000 additional reproducible manuals**, for **10,000 available volumes**. The 9,000 new books are *generated on demand*, not 9,000 static GitHub files.

The source-grounded documentation generator is `skeleton/forge/game_frontier_studio_worldline_handbooks.py`. Its 9,000 unique identities partition the entire new tier: 10 domains × 9 treatments × 10 directors × 10 worldlines. Each generated book documents 50 underlying source archetypes × 10 gameplay systems × 10 final passes (5,000 real source compositions), original-world authoring, exact operation examples, runtime sensor conditions and 30 acceptance checks.

Generate actual Markdown files and SHA-256 manifests from the repo root:

```sh
python -m scripts.export_game_studio_worldline_handbooks --out ./build/forge-books --all
```

Or export a bounded range using `--offset 0 --limit 25`.

The authenticated API also exposes `GET /api/game-frontier-authoring/handbooks` and `GET /api/game-frontier-authoring/handbooks/{domain}/{treatment}/{director}/{worldline}`. Search pages are limited to 64 and document bodies are bounded.

## Acceptance boundary

The focused test `skeleton/testing/test_game_frontier_studio_production_50000000.py` checks exact virtual indexing, real project source mutations, independently measured sensor proposals, deterministic persistence/rollback, Godot source export and handbook materialization. Full native playthrough, code-quality, copyright/IP and exact-head CI remain necessary before merge.
