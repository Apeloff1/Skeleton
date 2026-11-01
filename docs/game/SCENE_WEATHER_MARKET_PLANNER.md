# Replay-verified weather market route planner

`weather-market-plan` searches legal, deterministic caravan actions while
preserving all weather gates, collision checks, item pickups, delivery
dependencies, deadlines, commission rules, and earned reputation.

```bash
python -m skeleton weather-market-plan demo
python -m skeleton weather-market-plan solve --source-json "$MARKET_SOURCE" --max-states 128 --max-depth 16
python -m skeleton weather-market-plan solve --session-json "$VERIFIED_CHECKPOINT"
python -m skeleton weather-market-plan verify --report-json "$ROUTE_REPORT"
```

Candidate terminal routes are ranked by verified net currency, then earned
early-delivery reputation, then fewer actions. The planner never awards
currency itself. It replays the winning witness from the original checkpoint
and packages the complete canonical market save. Results are deterministic.

Search is bounded to 128 unique playable states and 16 actions. If exploration
is exhausted, a found route is labelled `feasible_unproven` rather than
optimal; no route becomes `inconclusive` rather than unreachable. Only a
fully explored bounded graph may return `optimal_within_bounds`. This is not
a claim of global optimality beyond the authored search limits.

Verification independently reruns the same bounded search and checks the
full report, action witness, nested weather/delivery saves and settlement
package. Receipts provide replay integrity, not cryptographic authorship.
