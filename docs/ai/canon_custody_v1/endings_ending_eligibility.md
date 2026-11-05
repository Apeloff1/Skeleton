# ending eligibility — endings canon custody

## Narrative contract
The `endings_ending_eligibility` system ensures that authored endings story facts are recorded as immutable, causally linked canon events. A record names one entity, fictional world, story tick, expected revision, original source evidence and optional predecessor. It is not a general-purpose text search or implicit truth detector.

## State and constraints
- Policy identity: `endings_ending_eligibility`
- Canon domain: `endings`
- Evidence classification: `custodian`
- Maximum records per in-memory ledger: `96`
- Maximum allowed subsequent tick gap: `8`
- World scope: explicit and immutable per ledger
- Entity scope: validated on causal predecessor
- Versioning: monotonically increasing integer revisions
- Event identity: unique per accepted record

## Event actions
1. **Establish** a new, previously unestablished world entity fact without a predecessor.
2. **Amend** an existing entity fact by referencing an accepted record for the same entity.
3. **Reconcile** an earlier fact through a new immutable record without erasing prior canon.
4. Query the `timeline` projection for an entity without advancing the ledger.
5. Query the `snapshot` projection for current revision and bounded metadata.

## Causality and uniqueness
An establishment must not include an earlier causal parent; an amendment or reconciliation must include one. Referencing a missing, future, unrelated, or self-referential parent is never accepted. Every record is appended at exactly the next revision with a larger story tick. A cross-world event cannot contaminate the ledger.

## Authoritative integration
1. Bind the storyteller actor and game world instance to a trusted authorization context.
2. Validate evidence provenance from the world-event service.
3. Load the current durable canon ledger and its latest revision.
4. Provide a command with a unique event ID and expected revision.
5. Apply the pure `append` function to compute a candidate state and decision.
6. Persist the candidate ledger, event evidence and receipt through a compare-and-swap transaction.
7. Publish the accepted canon change only after commit succeeds.
8. Preserve rejected candidate payloads separately for adjudication; do not treat them as canon.

## Failure containment
- Duplicate record IDs cannot be replayed as new facts.
- Stale revisions reject concurrent state writers.
- Cross-world commands reject instead of silently cloning facts.
- World ticks must be increasing, with bounded discontinuity.
- A missing predecessor never becomes an implicit new timeline branch.
- A reference crossing entity identity rejects even when the record exists.
- Unproved facts do not create accepted canon records.
- At ledger capacity, pause the writer and require a reviewed durable checkpoint rather than deleting history.

## Evidence trust model
Evidence IDs are opaque strings and must be authenticated by the hosting world runtime. Their format alone does not establish factual correctness. A model's narrative suggestion should remain a proposal until verified and committed by the canonical authority.

## Tests and delivery gates
Run `python -m pytest -q skeleton/testing/canon_custody_v1/test_endings_ending_eligibility.py`. Compile the Python source, parse its JSON Schema and the synthetic causal scenario, and execute exact-head repository CI/security gates. These references do not establish full 100-chapter continuity, consumer-device qualification, playable completeness, originality review, or release certification.

## Expansion work
Typed entity schemas, inter-entity causality, parallel-world merges, plot-hole search and large-scale archive compaction require separate explicit contracts. A merge across worlds should carry a source-world proof, deterministic conflict resolution and audit trail; never bypass the world scope by directly copying records.
