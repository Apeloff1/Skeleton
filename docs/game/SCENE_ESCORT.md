# Scene Escort — replay-proven convoy delivery

Studio B's `scene-escort` is an original offline escort vertical over the canonical
scene-mission engine. It does not duplicate world traversal, quest decisions,
inventory pickups, or ending resolution: those are executed by the existing
source-bound mission runtime. An escort can be delivered only after the mission
actually reaches its authored winning ending in the destination scene.

Run `python -m skeleton scene-escort demo` for the playable original
lantern caravan. Run `python -m skeleton scene-escort-author demo` for a
transactional authoring preview with an importable portable game bundle.
The `simulate`, `resume`, `verify`, `export`, and `import` verbs accept
bounded JSON values through explicit command flags; `--help` shows syntax.

An escort action is either `{"kind":"protect"}` or
`{"kind":"mission","action":<canonical mission action>}`.
Protect spends exactly one supply earned from an authored scene pickup and
reduces the next travel transition's damage by one. Protection cannot be
stacked. Every actual scene transition incurs authored travel and destination
hazard damage. If integrity reaches zero, the convoy is lost, further actions
fail closed, and no reward is granted. A terminal mission that does not reach
the specified destination with a winning scene outcome also loses the convoy.

The author document stores a genesis source, ordered typed edits, a source
digest, revision, and replay-verifiable digest. Editors must supply the exact
previous revision and source digest. Supported edits change integrity, travel
damage, reward, destination, hazards, and which authored pickups count as
supplies. The editor rejects non-authored locations/pickups and stale writes.
A preview uses the real gameplay runtime and produces a portable bundle.

Saves contain canonical source identity, a complete ordered action journal,
state digest, event-bus digest, and chained save metadata. Import reconstructs
the state from actions and verifies the bounded portable envelope. Checksums
detect corruption, not signatures or third-party authorship. Source changes
invalidate old sessions; no dynamic scripts, provider access, or untrusted
reward grants are supported.

Acceptance: `python -m pytest skeleton/testing/test_scene_escort.py
skeleton/testing/test_scene_escort_author.py -q`. Also run required
exact-head repository CI before promotion or merge; passing this focused
test alone is not release or device qualification.
