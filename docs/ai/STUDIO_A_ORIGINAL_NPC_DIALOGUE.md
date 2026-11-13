# Studio A — Original NPC cast, dialogue and playable continuity

`world-cast` authors an original character roster and source-bound dialogue
for a canonical Jeeves world. The browser player presents authored lines at
their scene and only after required world flags are actually earned. This
is playable, not a static character catalog. Each player choice uses the same
canonical transition and flag-grant semantics as the world compiler.

## Author, edit, review, compile, verify

```sh
python -m skeleton world-cast --store ./private propose --world-id cinder --npc-id ferryman --npc-name "The Ferryman" --npc-line "The marsh remembers every promise."
python -m skeleton world-cast --store ./private inspect --world-id cinder
python -m skeleton world-cast --store ./private edit --world-id cinder --expected-digest <old-cast-digest> --operation-file ./reviewed-edit.json
python -m skeleton world-cast --store ./private approve --world-id cinder --expected-digest <new-cast-digest> --note "Original author reviewed."
python -m skeleton world-cast --store ./private compile --world-id cinder --expected-digest <approved-cast-digest>
python -m skeleton world-cast --store ./private verify --world-id cinder
```

The typed edit envelope supports batched add/replace/remove operations for
actors and lines. Each transaction validates the complete final source:
actor IDs, roles, per-scene presence, unique dialogue order, canonical
Unicode, known flags and satisfiable dialogue preconditions. Every edit
revokes approval; stale source leases cannot be silently published.

The compiled HTML5 player is self-contained, CSP-hashed, offline and
renders only through DOM `textContent`; it does not evaluate arbitrary
code or load network assets. Its companion manifest contains world proof,
cast source and author review metadata. A receipt binds the HTML and JSON
artifacts to exact world/cast digests; verification independently recompiles
and checks bytes. Files use descriptor-anchored no-follow private custody
and per-world locks. The source can be authored from an operator's prompt
without claiming an external model generated any content.

Focused regression fixtures live in
`skeleton/testing/test_jeeves_world_cast.py`. Operator review is not
independent provenance verification, device qualification, CI acceptance,
security certification or consumer release.
