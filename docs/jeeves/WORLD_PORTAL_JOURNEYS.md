# Original multi-world portal journeys

This Studio A source-complete vertical connects two or more independently
proven original worlds through explicit reviewed portals. Each portal starts
at a source world's proven ending and enters the destination world's canonical
start. No existing world choice or flag is rewritten. The offline player
retains per-world flag state, offers deterministic choices and portal buttons,
and limits each session to 256 moves.

Create both original worlds with `world-canon`, then use:

`python -m skeleton world-portals --store PRIVATE_ROOT propose --network-id
two_worlds --prompt "Original linked journey" --root-world harbor
--from-ending resolution --to-world forest`

Edit the resulting typed JSON to add worlds, exact SHA-256 source leases and
sorted portals. Every world must be reachable from the root; every source
portal must point at an actual ending. `save --network-json JSON --create`
creates the initial private source. Subsequent edits require
`--expected-network-digest SHA`. Only `approve --expected-network-digest SHA
--review-note TEXT` may approve. `compile --expected-network-digest SHA`
writes a CSP-hashed standalone HTML5 player and a receipt published last.
`verify` independently reconstructs the player, source proof and receipt.

The custody layer uses descriptor-anchored reads, exclusive multi-world locks
and source-digest comparison; stale worlds, concurrent edits, symlinks, forged
approvals, missing travel links and tampered artifacts fail closed. This is a
source-verifiable playable handoff, not a device, rights or release certificate.

Focused regression: `python -m pytest skeleton/testing/test_jeeves_world_portals.py -q`.

Before review, `editor --network-id two_worlds --expected-network-digest SHA`
writes a CSP-bound offline visual portal editor into private custody. Add or
remove portals, export unapproved typed JSON, then submit it through the
optimistic `save` lease. The browser cannot approve or publish. The
read-only Jeeves `world.portals_propose_preview` tool accepts a root world,
network ID, original prompt, ending and destination; its output is never
implicitly approved or persisted.
