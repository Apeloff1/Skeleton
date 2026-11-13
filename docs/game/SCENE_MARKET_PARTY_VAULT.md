# Cooperative market save vault

The installed command `python -m skeleton scene-market-party-vault` provides
replay-verified offline save slots for authored cooperative market campaigns.

## Play and verify

- `scene-market-party-vault demo` creates an original authored market party,
  plays two canonical turns, and commits a checkpoint to a source-bound slot.
- `scene-market-party-vault accept` plays a full canonical campaign, saves
  at a split, serializes/restores the vault, resumes remaining turns, and
  verifies the earned victory and portable party/vault round trips.
- `create --source-json JSON` starts an empty source-bound vault.
- `transact --vault-json JSON --action-json JSON` applies a put/delete using
  an explicit expected revision and expected prior slot state digest.
- `slot --vault-json JSON --slot NAME` returns the verified canonical party
  checkpoint; `verify`, `export`, and `import` validate replay and portability.

The vault never awards credits, items, achievements or victory. Only the
canonical market/party reducers can produce those states. Journal receipts
are recomputed from the source and every stored event. Recomputing an export
checksum cannot conceal a forged checkpoint, edited event, stale lease, or
source mismatch. A deleted slot is absent after replay; history is retained.

Limits: eight named slots, 24 journal operations, two MiB serialized payload,
and the canonical party engine's own turn/JSON budgets. On any failure, the
operation raises an error and does not mutate the caller's input. The vault
is an offline integrity and compare-and-swap facility, **not** an
authentication or multi-device synchronization protocol. Imported data must
remain untrusted until replay validation completes. No release or device
qualification is implied by structural receipts.
