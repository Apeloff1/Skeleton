# Machine repository protocol

The repository machine plane exposes deterministic analysis for autonomous
agents. Its outputs are advisory evidence and scheduling metadata.

## Request model

The Python protocol accepts only typed operations:

- `overview`
- `search`
- `hotspots`
- `debt`
- `reorganization`
- `session`
- `context`

It intentionally does not accept arbitrary shell commands, code strings,
workflow permissions, executable paths, tokens or mutation instructions.

## Session packet

A session contains:

- exact repository machine fingerprint;
- up to three conflict-aware selected objectives;
- coordinator health/topology summaries;
- bounded retrieval hints;
- invariant constraints.

If the full payload exceeds its byte budget, advisory sections are compacted
while selected work and safety constraints remain present.

## Persistent state

The machine plane defines optional durable primitives:

- a fingerprint-bound work queue;
- conflict-key leases;
- steward checkpoints and fairness counters;
- an append-only architecture ledger.

These primitives are safe to use only through a persistence mechanism whose
authority is already approved. Creating the data model does not itself grant
permission to commit state to the repository.

## Structural mutation

Reorganization and refactor modules emit plans only. Mutation must continue
through the repository's normal Secretary/Worker authority and exact-head
validation.

After a structural mutation:

1. rebuild the repository model;
2. compare model/evolution deltas;
3. verify no new dependency cycles;
4. check unclassified-surface growth;
5. execute focused tests and required integration/security gates;
6. refresh queue items bound to the old fingerprint.

## Scaling

For large repositories, use context shards and per-zone context allocations.
Agents should retrieve the smallest zone/file set required for the selected
objective rather than loading the entire repository into model context.
