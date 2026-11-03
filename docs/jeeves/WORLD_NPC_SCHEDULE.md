# Original NPC schedule — reviewed source-bound scene availability

`world-npc-schedule` turns an original prompt into a typed NPC appointment
linked to the exact canonical world and cast digests. A schedule names the NPC,
scene, first and last scene tick, flag preconditions and original encounter
label. It is never approved by a model.

Operator workflow: `propose` → review JSON → `save --create
--schedule-json JSON` → `edit --expected-digest DIGEST
--operation-json JSON` → `approve --expected-digest DIGEST
--review-note TEXT` → `compile --expected-digest DIGEST` → `verify`.

The proof performs bounded breadth-first exploration of scene/flag/tick states,
rejects double-booked NPC windows, absent cast actors, impossible appointments
and stale world/cast revisions, and emits a deterministic choice witness for
each appointment. Every edit resets review. The offline HTML5 player uses the
same authored world choices and earned flags to show present NPCs and dialogue.
No network access, external assets, eval or implicit approvals are used.

The `world.npc_schedule_propose_preview` and
`world.npc_schedule_preview` Jeeves tools are read-only; only the operator
CLI may persist, approve and compile. Descriptor-anchored private files and
optimistic digest leases protect source and artifact publication. Compiled
source proof is not a native device or release certification.

The `editor --expected-digest DIGEST` command publishes a CSP-hashed,
network-disabled browser editor. Authors can add/remove appointments, load
typed JSON, and export an unapproved source document for `save` and
subsequent explicit `approve`. The editor never writes canonical source or
self-approves an edit.
