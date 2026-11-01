# Eight-entrant combat league — playable offline season

Entry point: python -m skeleton combat-league demo

A complete original three-round Harbor League uses eight distinct combatants,
two four-entrant canonical brackets per round, and distinct balanced round partitions.
Each bracket runs the existing turn-combat tournament and its source-bound
replay/save engine. Semifinal wins earn two points; final wins earn three
additional points; finalists earn one additional point. The highest scoring
entrant wins the league; tied points resolve by stable entrant ID.

CLI verbs: demo, simulate --source-json JSON, advance --session-json JSON,
resume --session-json JSON, verify --session-json JSON,
standings --session-json JSON, export --session-json JSON,
import --bundle-json JSON. Each command emits canonical JSON. Failed input
returns exit code 2 without creating a result.

The league is authored with exactly eight entrants, one to four rounds,
and bounded match turns. Replays reconstruct every match, point award,
ranking and save lineage; no client-provided standings are trusted.
Input is limited to 2 MiB, with strict duplicate-key/nonfinite rejection.
Portable checksums detect corruption, not author identity or rights.
All original names and stat values are owned content, not third-party assets.

Focused acceptance: python -m pytest skeleton/testing/test_combat_league.py -q
