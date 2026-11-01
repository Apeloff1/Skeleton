# Source-bound NPC rendezvous

The NPC rendezvous compiler checks whether two already-authored NPCs can meet
at a known scene site within an operator-authored time window. It composes
canonical source and quest replay, the temporal schedule and directed NPC transit
graph. It does not infer actual distances, animate a meeting or claim native
runtime qualification.

Workflow: obtain a canonical transit receipt; run the CLI with
\`--prompt\` for a deterministic first encounter or \`--meetings\` with
an exact JSON list. A meeting has \`id\`, two distinct \`npc_ids\`, a known
\`site\`, \`earliest_tick\`, \`latest_tick\` and \`duration_ticks\`.
The latest tick is the exclusive end boundary for the meeting.

Use \`--editor-directory\` to publish a CSP-hashed offline HTML editor in an
existing private directory. Export the typed JSON and pass it back through
\`--import-meetings\` with \`--baseline-rendezvous\` and the original
\`--transit\` receipt. The CLI replays the baseline and rejects a stale source,
session or transit digest. Use \`--publish\` for no-overwrite, fsynced private
custody, and \`--restore\` to verify the stored receipt against canonical source.

Jeeves exposes \`studio_original_npc_rendezvous\` through the static typed
world-tool router. Untrusted arguments cannot authorize execution. Meeting
reservations are deterministic, ordered and fail closed on missing routes,
overlapping scene occupancy or incompatible timing. Handoff requires all
meetings and the baseline transit to be feasible. The handoff references the
canonical HTML5 quest bundle but explicitly does **not** claim the meeting is
rendered, that travel is physical, or that any release/device check passed.

Focused tests: \`pytest -q tests/test_studio_ecosystem_npc_rendezvous.py\`.
Run required exact-head CI before any promotion or merge.
