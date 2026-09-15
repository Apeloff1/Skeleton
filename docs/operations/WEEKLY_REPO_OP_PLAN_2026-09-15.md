# Skeleton repository: seven-day operating plan

Window: 2026-09-15 through 2026-09-21

Primary objective: convert the current frontier consolidation branch into a mergeable, testable integration baseline, then promote the strongest unique behavior from the source repositories without copying applications, catalogs, provider dependencies, or duplicate primitives.

## Operating rules

- Work through small contract-backed increments even when the overall workload is large.
- Promote behavior, invariants, adapters, and tests; do not wholesale-copy source applications.
- Preserve exact source repository/path/blob provenance for every promoted behavior.
- Prefer one canonical primitive plus adapters over sibling implementations.
- Keep provider/database/framework dependencies outside the frontier kernel unless evidence proves they belong there.
- Every promotion must ship with deterministic tests and a rollback-sized commit.
- A red security or contract gate blocks deeper integration work until fixed.

## Day 1 — Stabilize frontier PR #83 and harden runtime

Goals:
- Restore repo-wide CI compatibility for the frontier workflow.
- Keep the existing runtime/memory/NPC contracts as the canonical boundary.
- Promote GameForge duplicate-suppression semantics without importing MongoDB/outbox infrastructure.
- Record the week plan and update source lineage.

Acceptance gates:
- Frontier workflow uses immutable action SHAs and disables checkout credential persistence.
- Frontier contract suite remains green.
- Agent execution accepts optional idempotency keys, coalesces concurrent duplicates, replays completed results, bounds retained keys, and fails closed on key reuse with a different payload.
- Raw idempotency keys are not written to provenance; only a SHA-256 digest is recorded.
- Promotion manifest names the exact GameForge source blob and the deliberately deferred infrastructure.

## Day 2 — Promote pure world policy, not world infrastructure

Primary sources:
- `Apeloff1/Lorebuffa/backend/world_map.py`
- byte-equivalent `Apeloff1/Openworld/backend/world_map.py`

Work:
- Characterize region lookup, route distance, voyage supply policy, fog-of-war projection, and random-island policy.
- Verify there is no stronger incumbent world-policy primitive in Skeleton.
- Extract only deterministic/pure policy into one frontier/world module.
- Inject randomness and clock inputs wherever source behavior is nondeterministic.
- Leave FastAPI routes, Motor/Mongo clients, persistence handlers, and the full world catalog in source repositories.

Acceptance gates:
- One shared lineage entry for the equivalent Lorebuffa/Openworld blob.
- Deterministic unit tests for every promoted rule.
- No new database or web-framework kernel dependency.
- No copied catalog payload.

## Day 3 — Memory conformance and retrieval evidence

Primary sources:
- `Apeloff1/Prood/backend/services/rag_service.py`
- byte-equivalent Tutolage RAG implementation

Work:
- Turn memory behavior into an explicit backend conformance harness shared by `InMemoryStore`, `CollectionMemoryAdapter`, and `SQLiteCollection`.
- Cover put/upsert, retrieval, metadata filtering, delete, stable IDs, and relevance normalization.
- Add reproducible benchmark fixtures for small/medium corpora and filtered retrieval.
- Characterize an optional real vector backend only behind the existing collection adapter; do not make it a kernel dependency.

Acceptance gates:
- Same conformance suite passes against every supported backend.
- Benchmark evidence is checked in as data or reproducible output instructions.
- Prood/Tutolage duplicate source blob remains adapted once.
- No provider-specific type leaks into `MemoryContract`.

## Day 4 — NPC/domain integration without a second hierarchy

Primary sources:
- Prood NPC pipeline as incumbent semantic generator.
- Lorebuffa/Openworld expanded NPC records as domain data sources.

Work:
- Expand fixture coverage for schedules, factions, quests, shops, voice style, disposition, and source IDs.
- Add round-trip/normalization tests proving source-domain fields survive through `NPCSpec.metadata`.
- Characterize world-state interactions as policies/adapters rather than new NPC classes.
- Reject duplicate generators or catalog copies.

Acceptance gates:
- One canonical `NPCSpec`/generator path.
- Domain-specific data remains metadata/adapters.
- Fixture and normalization tests cover representative source records.
- No 1:1 copy of the large source NPC catalogs.

## Day 5 — Runtime/events durability boundary

Primary source:
- `Apeloff1/gameforge-rs/crates/gf-core/src/lib.rs`

Work:
- Compare the frontier `EventBus`, resilience controller, provenance digest, and new idempotency behavior to GameForge guard/outbox semantics.
- Specify a minimal durability boundary before implementing persistence.
- Promote only behavior that can remain provider-neutral: backpressure semantics, typed state transitions, explicit acknowledgement/confirmation states, and deterministic retry policy.
- Keep MongoDB client setup and background infrastructure outside the kernel.

Acceptance gates:
- No duplicate event bus or persistence primitive.
- Any new durability interface has a dependency-free reference implementation and failure tests.
- Backpressure is explicit; unconfirmed work is never silently discarded.
- Cancellation/retry behavior is deterministic and documented.

## Day 6 — Repo-wide quality, security, and mainline convergence

Work:
- Reconcile PR #83 with all security/quality changes that landed on `main` after the branch point.
- Run/inspect backend quality, workflow-security, secret-hygiene, SAST, syntax, lint, frontier contracts, and route coverage gates.
- Remove obsolete compatibility code, dead imports, duplicated fixtures, and completed temporary artifacts.
- Verify GitHub Actions use immutable pins, least permissions, and hardened checkout settings.
- Review changed dependencies and generated/binary growth.

Acceptance gates:
- Required CI is green or every remaining failure is proven unrelated and tracked.
- No known secret, workflow-hardening, high-confidence SAST, or syntax regression.
- No duplicate frontier primitive introduced during the week.
- Branch diff remains reviewable and provenance-complete.

## Day 7 — Consolidation closure and next-wave handoff

Work:
- Run the full frontier acceptance matrix and benchmark set.
- Update consolidation matrix, architecture notes, promotion manifest, and lineage inventories.
- Compare branch against current `main` and remove superseded work.
- Mark PR #83 ready for review only after its current scope is internally complete.
- Split future world/application work into a new PR if it would make #83 materially harder to review.
- Produce the next seven-day backlog from measured gaps rather than repo size or LOC targets.

Acceptance gates:
- Contract, integration, provenance, security, and benchmark gates all have explicit evidence.
- PR description matches the actual delivered surface.
- No completed TODO remains disguised as future work in the current scope.
- The next wave starts from a green mainline-compatible baseline.

## Week scoreboard

Track these after every integration increment:

- Required CI workflows: pass/fail and failing step.
- Frontier contract tests: total passed, failed, skipped.
- Promotion manifest: count of source blobs promoted/adapted/rejected.
- Duplicate primitives introduced: target `0`.
- New mandatory kernel dependencies: target `0` unless explicitly approved by evidence.
- Security-gate regressions: target `0`.
- Unproven source copies/catalog imports: target `0`.
- Open integration candidates with deterministic tests: trend downward through the week.

## Day-1 execution log

- Hardened `.github/workflows/frontier-contracts.yml` to the repository workflow-security policy.
- Added bounded provider-neutral idempotent execution to `AgentRuntime`, derived from GameForge typed duplicate-suppression semantics without importing its persistence stack.
- Added tests for completed replay, concurrent request coalescing, conflicting key reuse, and invalid empty keys.
