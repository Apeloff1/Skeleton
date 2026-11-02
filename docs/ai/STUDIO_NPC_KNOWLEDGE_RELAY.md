# Studio A — source-leased NPC knowledge relay

The relay compiler is an original-world authoring vertical connecting canonical
quest source, earned NPC fact exchange, authored rendezvous, scene scheduling,
Jeeves typed dispatch, private CLI edits, deterministic replay, and guarded
HTML5 playable handoff. It does **not** claim real speech, model inference,
native NPC memory, hardware qualification, or release certification.

Use `scripts/studio_npc_knowledge_relay_cli.py --project <id>
--expected-source <64-character digest> --exchange-file <private receipt>
--prompt` to generate a deterministic proposed relay. To edit, supply a
private JSON file with exactly `{"routes":[...]}` and use
`--authoring-file <path>`. A route specifies `fact_id`,
`recipient_scene_id`, `target_scene_id`, and one to eight explicit
`{"meeting_id": "...", "to_npc_id": "..."}` hops.

Each hop must connect two distinct source-known NPCs via an actual authored
meeting, preserve causal order, and end at a later authored scene owned by the
final recipient. The compiler refuses fabricated facts, unknown meetings,
duplicate routes, cycles, stale source/session leases, and replay forgery.
Blocked routes never expose original fact text. A logical accepted meeting is
not proof of spoken dialogue. The typed Jeeves registry name is
`studio_original_npc_knowledge_relay`; operator authorization is out of band.

`--publish <existing-private-directory>` writes an immutable, private,
no-follow, fsynced `npc_knowledge_relay.json` receipt. `--restore <dir>`
reads it under strict ownership, permissions, type and size limits, then
recompiles from current canonical source. `--playable` fails closed unless
every authored route is earned and the underlying exchange handoff is valid.
The resulting bundle is the existing canonical HTML5 quest proof, **not**
native NPC dialogue. Run
`pytest -q tests/test_studio_ecosystem_npc_knowledge_relay.py
tests/test_studio_world_tool_router.py` on the exact branch head.

The optional `--render-editor <existing-private-directory>` writes a
CSP-hashed, script-restricted offline HTML editor with a typed JSON download.
The exported record is leased to the exact source, session, exchange and
baseline relay digest. Recompile it with `--editor-export-file <private-path>`,
`--baseline-relay-file <private-baseline-receipt>` and
`--exchange-file <private-exchange-receipt>`. Import never grants authority
from JSON, and a changed baseline fails closed rather than overwriting work.
