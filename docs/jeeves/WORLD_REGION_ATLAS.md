# Original world region atlas

This Studio A vertical links an authored world prompt to reviewed region placement,
choice-bound travel corridors, durable edits, a compiled offline HTML5 playable,
and deterministic verification. It does not invent rights or approve travel automatically.

Start with an existing reviewed world created using `world-canon`. Use
`python -m skeleton world-atlas --store PRIVATE_ROOT propose --world-id voyage --prompt "Map the coast"`
to obtain the typed JSON proposal. The default puts all scenes in one original
region. Edit the proposal to add regions, sorted scene placements, and one
passage per cross-region canonical choice; do not change the world digest.

Submit the JSON using `world-atlas ... save --world-id voyage --atlas-json JSON
--expected-world-digest SHA --create` for the first write. Later saves require
`--expected-atlas-digest SHA` as an optimistic edit lease. `inspect` reports
the current exact source and ending itineraries. Explicitly approve with
`approve --expected-atlas-digest SHA --review-note TEXT`, then
`compile --expected-atlas-digest SHA`, and finally `verify`.

The compiled HTML retains the canonical playable's Content Security Policy
and appends accessible original region descriptions. A passage never grants
a flag or rewrites a world choice; it annotates an existing verified transition.
An atlas cannot compile when the source changes, a scene is unplaced, a crossing
lacks a passage, approval is absent, or the source/artifact receipt is tampered.

The typed `world.atlas_preview` Jeeves tool is read-only and returns the
source digest, reviewed status, region occupancy and ending travel witnesses.
The operator CLI is the only atlas write authority. Focused regression:
`python -m pytest skeleton/testing/test_jeeves_world_atlas.py -q`.
Release/device/engine qualification remains a separate required gate.

For visual authoring, run `world-atlas ... editor --world-id voyage
--expected-atlas-digest SHA` before approval. The command writes a CSP-hashed,
network-disabled HTML editor into the private store. Open it offline, edit
regions, scene placement and travel passages, then export JSON. Submit the
export through the same optimistic `save` transaction; browser export never
approves, writes to custody, or bypasses server-side atlas validation.

The `world.atlas_propose_preview` Jeeves tool accepts an original prompt and
returns a typed draft without writing custody. Only `approve` can change the
approval bit; `save` rejects any preapproved JSON to prevent review bypass.
