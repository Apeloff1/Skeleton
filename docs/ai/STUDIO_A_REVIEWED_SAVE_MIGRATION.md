# Reviewed original-world save migration

An operator can revise an authored world without silently rewriting a player's
earned choices. A new target save slot is published only after the old source,
checkpoint, explicit choice-ID map, and current canonical target all pass a
deterministic replay proof. This is an opt-in migration, not an automatic upgrade.

The old world and checkpoint are local, bounded JSON inputs. A portable checkpoint
contains a SHA-256 integrity checksum, **not a cryptographic signature**. Import
does not authenticate the original author. Only trusted operator-supplied files
should be used for production migration; no private source is embedded in the
receipt. The target world is always re-read from descriptor-anchored custody.

## Operator workflow

1. Export the old save before revising the world:
   `python -m skeleton world-session --store PRIVATE export --world-id tides --slot original`.
   Save the checkpoint and the exact old canonical world in separate JSON files.
2. Publish the revised, independently proved world through the normal world
   canon review process.
3. Preview without mutation:
   `python -m skeleton world-migrate --store PRIVATE preview --world-id tides --old-world-file OLD.json --checkpoint-file SAVE.json`.
   Optional `--choice-map-file MAP.json` maps old choice IDs to renamed new IDs.
4. Review the returned world digests, choice trace, earned flags, ending and
   playable proof. Copy the `preview_digest` as the optimistic lease.
5. Apply to a **new** slot:
   `python -m skeleton world-migrate --store PRIVATE apply --world-id tides --old-world-file OLD.json --checkpoint-file SAVE.json --slot migrated --expected-preview-digest DIGEST --review-note "Approved after replay review"`.
6. Resume using `world-session inspect/choose`, and compile the target world
   with `world-canon` using the target source digest. No release/device
   qualification is implied by source replay.

A renamed choice may change its visible label but cannot change its source or
destination scene, required flags, or granted flags. Existing scenes and flags
must replay identically, including a completed ending label. Changed causal
semantics, unearned flags, mismatched world IDs, stale previews, invalid maps,
existing slots, symlinked files and lease conflicts fail closed. The source
revision is rechecked under the same exclusive world lock used by session
writes. The new save is the only published object, avoiding partial
multi-artifact migration receipts.

Typed Jeeves `world.migration_preview` is read-only. It cannot approve or
publish a migrated slot. Explicit operator review is mandatory.
