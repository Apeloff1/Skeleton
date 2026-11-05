# Guard Patrol Scene Gameplay

Run \`python -m skeleton scene-patrol demo\` for a playable original
Lantern Hollow patrol encounter. The guard alternates between the quay
and gate each player turn. Collect the brass key, time a route, and
reach the authored sanctuary ending. \`wait\` advances the guard clock
without silently moving the player or granting items.

The source is \`skeleton.scene_guard_patrol.v1\` with a canonical
\`scene_travel.v1\` world and one to eight guards. Every guard has a
unique ID, two to eight distinct traversable patrol rooms, a bounded
offset, authored blocked exits and an optional earned bypass item.
Routes must form a directed loop through existing exits. Invalid
routes, unknown exits, forged inventory and out-of-bounds actions
fail closed. Existing item gates and scene endings remain authoritative.

Use \`new --source-json\`, \`step --session-json --action-json\`,
\`inspect\`, \`verify\`, \`export\` and \`import\` for source→runtime
→portable checkpoint round trips. Replay reconstructs each action,
guard location and parent-linked save from the source. Bundle checksums
detect corruption but do not authenticate authors or confer rights.
