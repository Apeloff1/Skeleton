# Frontier milestones 6 and 7

Candidate-only. No GPU claims.

## M6 — Session orchestrator
`game_frontier_session.py` — ordered compose steps with verified replay.

## M7 — Campaign ledger
`game_frontier_campaign.py` — aggregates verified sessions, compares two
campaigns, and emits a content-addressed audit receipt.

## Index
`game_frontier_milestone_index.py` — catalogs P0 through M7.

## Tests
- `test_game_frontier_campaign.py` — 7 passed
- `test_game_frontier_milestone_index.py` — 4 passed
