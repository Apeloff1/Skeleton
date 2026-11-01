# Transactional caravan market authoring

`weather-market-author` edits authored commissions and early-delivery
reputation rules without altering the canonical delivery rewards, map,
weather simulation, inventory or movement rules.

```bash
python -m skeleton weather-market-author demo
python -m skeleton weather-market-author edit --source-json "$SOURCE" --operations-json "$EDITS" --expected-digest "$SOURCE_DIGEST" --actions-json "$PREVIEW_ACTIONS"
python -m skeleton weather-market-author verify --source-json "$SOURCE" --receipt-json "$RECEIPT"
```

Each operation names a canonical delivery and exactly one of:
`set-commission` (basis points, 0–5000),
`set-early-threshold` (ticks, 1–64), or
`set-reputation` (points, 0–100). An edit batch is bounded to 16
operations; duplicate target fields, no-op batches, unknown deliveries,
invalid numeric types, and stale source digests fail atomically.

The result includes the fully normalized new source, before/after digests,
the original operations, an optional replayed playable preview, and a
deterministic receipt. Verification reapplies the edits from the original
source and replays the preview. The caller retains the unchanged original
source and must explicitly accept the edited source for subsequent play.
Receipts are integrity evidence, not author signatures or permission grants.
