# Cooperative market vault revision recovery

The installed `python -m skeleton scene-market-party-vault-history` command
extends the source-bound cooperative save vault without introducing a second
gameplay reducer, duplicating currency, or rewriting earned history.

## End-to-end workflow

Run `scene-market-party-vault-history accept` to play an original authored
campaign, save an intermediate checkpoint, complete the campaign, preview
restoring the earlier checkpoint, commit that recovery as a new compare-and-swap
event, replay the remaining player turns to the same earned victory, and verify
portable party and vault exports.

For a real vault JSON document, use `history --vault-json JSON --start 0
--limit 8` to page original receipts. Use `seek --vault-json JSON --revision
N` to reconstruct a historical vault; use `diff --vault-json JSON
--from-revision N --to-revision M` to inspect slot state-digest changes without
exposing the checkpoint payload.

To restore one slot, use `preview --vault-json JSON --target-revision N
--slot NAME --expected-revision CURRENT`. This returns an immutable preview
containing the exact leased put/delete action and its replay-derived outcome.
Pass that unchanged preview to `apply --vault-json JSON --report-json JSON`
to create a **new** vault revision. Re-verify the returned vault or export it
with `scene-market-party-vault export`. No in-place files are modified by the
CLI; the caller controls durable publication. `verify-history` and
`verify-preview` independently recompute their reports from canonical
replay, not from untrusted checksums alone.

## Guarantees and limits

- All snapshots are rebuilt from the original source and event journal.
  Arbitrary historical snapshots, altered receipts, and forged earned state
  are rejected before any recovery is proposed.
- Recovery uses both the current vault revision and the current slot digest.
  A stale parent or no-op recovery fails closed. An absent historic slot
  produces a delete only when the current slot exists; a previously deleted
  checkpoint can be restored only by replaying its original earned lineage.
- Recovery preserves all prior journal entries and appends a new leased event.
  A rollback is a new offline branch of play, **not** erasure, an authoritative
  multi-device merge, or permission to award credits.
- Existing vault limits remain eight slots, 24 events, two MiB of serialized
  JSON, and canonical party replay bounds. History pages are capped at 16
  events. Export checksums prove accidental/unauthorized editing detection
  only under the trusted local source; they are not cryptographic signatures,
  actor authentication, or secure key custody.

Focused tests cover stale leases, rehashed forged reports, corrupted nested
checkpoints, deleted slot restoration, bounded pages, JSON round-trips,
CLI errors, source-to-play/recovery/replay/export and unchanged parent inputs.
Exact-head CI and device qualification must pass independently before release.
