# Reviewed world scene events

`python -m skeleton world-events` is the operator-only path for original, one-shot
scene events. Jeeves exposes **read-only** `world.events_propose_preview` and
`world.events_preview` typed tools. It never implicitly approves or publishes.

## Author → edit → playable

1. Publish a reviewed canonical world with `world-canon`.
2. `world-events --store DIR propose --world-id bells --prompt "The bells wake" --event-id first_chime --scene opening --description "The bells ring" --requires-json '[]' --grants-json '["bell_awake"]'` returns an unapproved source.
3. `world-events --store DIR save --world-id bells --create --events-json '<proposal JSON>'` stores the original source. Copy the returned digest.
4. `world-events --store DIR editor --world-id bells --expected-digest DIGEST` writes a CSP-hashed offline editor; its JSON export is always unapproved.
5. `world-events --store DIR edit --world-id bells --expected-digest DIGEST --operation-json '{"action":"add","value":{...}}'` performs a source-leased edit.
6. `world-events --store DIR approve --world-id bells --expected-digest DIGEST --review-note "Original author reviewed"` records operator review.
7. `world-events --store DIR compile --world-id bells --expected-digest APPROVED_DIGEST` writes a deterministic HTML5 playable and receipt. `verify` re-computes both byte-for-byte.

## Semantics and limits

Events fire once, in sorted ID order, whenever their scene is entered and all
required flags are present. Each event grants at least one flag and may unlock
later events; fixed-point evaluation is bounded by 16 events. The verifier
explores at most 8,192 world/event states, rejects reachable dead ends and
unreachable events/endings, and produces deterministic event and ending traces.

Sources are limited to 512 KiB, HTML to 1 MiB. IDs, flags, text, source digests,
and CAS leases are validated. Source publication resets approval; a stale
world digest or stale edit fails closed. No network, eval, executable asset
imports, or implicit approvals are used. Existing world canonical proof still
applies; this vertical cannot silently rescue an otherwise invalid world.

The receipt qualifies only reviewed offline event gameplay, not native-device,
release, security-gate or performance certification.
