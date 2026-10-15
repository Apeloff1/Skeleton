# Native multi-emulator receipt analysis

The local comparison desk already operates two to ten native emulator lanes and exports a complete five-MiB-bounded input, frame, audio and reset receipt chain. This addition supplies the missing offline pairwise measurement stage, handling up to 45 unordered comparisons across those ten lanes.

Operator workflow: export native evidence JSON from the local desk, then run:

    python3 scripts/analyze_live_game_comparison.py --evidence /path/to/export.json --output-dir /path/to/reports

Outputs: live_pairwise_observations.json and live_pairwise_observations.html. The self-contained offline dashboard filters by game ID, showing checked native step counts, episode resets, controller activity, distinct video/audio hashes, within-episode frame/audio changes, and mean absolute differences in the four reported native observation signals.

Security and evidence: the existing native evidence verifier checks all source/core metadata and every chained step, reset and raw controller tape first. Imported JSON is capped at five MiB and cannot contain duplicate keys. A self-contained digest chain is not independently attested hardware execution. Reports do not claim identical game states, synchronized clocks, game quality winners, emulator fidelity, copyright clearance, or AI training success. Nothing downloads ROMs, executes games, or updates production model weights during analysis.

This is a 10-active-game observation facility, not the 30-game study scheduler and not a substitute for real source-rights-cleared native qualification.
