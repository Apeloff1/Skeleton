# Studio A — Verified world experience assembly

`world-experience` compiles a playable offline HTML5 world with both
original authored NPC dialogue and a reviewed route witness. It is a real
cross-feature integration path: the player can choose any legal canonical
world choice, see only earned dialogue, and receive route guidance while
their actual choice trace remains a prefix of the reviewed route.

## End-to-end source workflow

Create and edit the original world using `world-canon`. Use
`world-cast propose/edit/approve` to author and review NPC dialogue.
Use `world-route propose/inspect/approve` to review a source-proven
ending path. Each source is durably persisted under the same private
world custody directory, with its own expected-digest lease.

```sh
python -m skeleton world-experience --store ./private compile --world-id marsh --world-digest <world-sha> --cast-digest <cast-sha> --route-digest <route-sha>
python -m skeleton world-experience --store ./private verify --world-id marsh
```

The compiler requires explicit approval of **both** dialogue and route,
proves the world graph, independently replays the ending witness, checks
actor scene presence and reachable dialogue preconditions, and rejects
cross-source lease drift. It produces an offline CSP-hashed HTML5 player,
a typed experience manifest and an exact-artifact receipt. Verification
recomputes all outputs under one exclusive per-world source lock, reads
artifacts without following symlinks and checks every byte.

This handoff combines world, cast and route only; era assets, timeline,
hardware testing and deployment remain separate required qualifications.
The review receipt is not a claim of independent authorship certification
or consumer release. Focused regression fixtures:
`skeleton/testing/test_jeeves_world_experience.py`.
