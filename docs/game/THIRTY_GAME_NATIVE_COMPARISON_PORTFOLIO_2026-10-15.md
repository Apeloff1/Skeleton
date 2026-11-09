# Multi-batch emulator comparison across a 30-game study

The live libretro desk runs at most ten approved game lanes at once. This source-only portfolio joins **separately captured 2–10-game native evidence batches** against the original validated 30-game study manifest and its planned batch indices, without keeping thirty cores in memory.

Operator command:

    python3 scripts/analyze_game_comparison_portfolio.py --study /path/to/30_game_study.json --evidence /path/to/batch0.json --evidence /path/to/batch1.json --evidence /path/to/batch2.json --output-dir /path/to/reports

Results: emulator_30_game_portfolio.json and emulator_30_game_portfolio.html. The offline dashboard shows up to thirty observed games and 435 version pairs, series IDs and earlier/middle/after annotations, per-batch input steps and SHA-256 lineage, missing game IDs, and descriptive differences in native observation summaries.

All cohorts must have matching study ID/digest, approved registry digest, unique planned batch index, permitted game IDs, and the declared game/core/target/seed contract; each is reverified through the native receipt hash-chain verifier. Unrecorded games stay explicitly missing.

Cross-batch frames and game states are **not** synchronized. Reported means are not winning-game rankings or fidelity metrics. This does not execute an emulator, download ROMs, validate rights independently, inspect console hardware, automatically ingest knowledge, or promote model weights.
