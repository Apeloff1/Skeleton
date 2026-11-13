# Studio A — Source-bound world route authoring and playable witness

The `world-route` vertical connects a reviewed original world to a deterministic
route witness, private persisted edit, compiled offline HTML5 player and tamper
verification. It does **not** call an LLM or claim generated content was produced
by an external provider. Source is always an authored, typed Jeeves world.

## Operator workflow

First author and publish a world with `world-canon propose` and use
`world-canon edit` to add real scenes and choices. The world graph must pass
canonical ending and reachable-state proof.

```sh
python -m skeleton world-route --store ./private propose --world-id lantern --ending resolution --require-flag ticket
python -m skeleton world-route --store ./private inspect --world-id lantern
python -m skeleton world-route --store ./private approve --world-id lantern --expected-digest <draft-route-digest> --note "Reviewed by original author"
python -m skeleton world-route --store ./private compile --world-id lantern --expected-digest <approved-route-digest>
python -m skeleton world-route --store ./private verify --world-id lantern
```

The proposal is explicitly unapproved. `inspect` returns a deterministic
witness or a typed `route_unreachable`/`route_search_inconclusive` result.
The latter never pretends a bounded search proved impossibility. Approval
requires a real replayable witness and a nonempty review note. A changed world
invalidates the route lease, requiring fresh review.

## Contracts and custody

`jeeves.world.route_review.v1` is the source schema.
`jeeves.world.route_handoff.v1` contains the replayed, independently
verified sequence of scene IDs, choice IDs and earned flags.
`jeeves.world.route_receipt.v1` binds three artifacts by SHA-256:
a CSP-hardened standalone HTML5 player, a static offline route guide, and
the JSON witness. `verify` independently recompiles from canonical sources
and checks every artifact byte against its expected content.

Routes can require earned flags, forbid flags, exclude choice IDs and limit
search steps. Search is bounded by 2,048 states and 512 steps. Every replay
revalidates source identities, edge preconditions, earned flags and ending
eligibility. Files are stored using descriptor-anchored, no-follow POSIX
operations, a per-world exclusive lock and optimistic expected-digest leases.
Unsupported platforms fail closed.

## Qualification

The review receipt proves deterministic source integrity and an operator
decision, **not** external authorship, device testing, security certification,
CI qualification, production deployment or consumer release. The focused
regression suite is `skeleton/testing/test_jeeves_world_route.py`; required
exact-head GitHub gates remain separate and mandatory.
