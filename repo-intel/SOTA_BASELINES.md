# Repository intelligence SOTA baselines

Verified: **2026-09-16**. This is a design baseline, not a claim that Skeleton already matches every property listed here.

## Bazel — dependency/action graph + content-addressed caching + remote execution

Current Bazel documentation models builds as declared dependency/action graphs, exposes forward/reverse dependency queries, stores reusable outputs in an action cache plus content-addressable store, and supports remote execution to distribute build/test actions across machines.

Skeleton implication: the repo index must preserve forward/reverse graph structure, expose build-affecting inputs, use stable content identities, and leave room for action fingerprints / remote execution rather than stopping at path inventory.

Sources:

- https://bazel.build/query/quickstart
- https://bazel.build/versions/7.1.0/remote/caching
- https://bazel.build/remote/rbe

## Buck2 — fine-grained invalidation + deferred materialization

Buck2 documents DICE as an incremental computation graph that invalidates reverse dependencies and recomputes only required invalidated nodes. Buck2 also documents deferred materialization so remote build intermediates need not be downloaded until locally required; Meta reports substantial real-world speedups from that approach.

Skeleton implication: semantic/index objects should be blob-keyed and recomputed only for changed content; reverse dependencies should be materialized for impact; future build artifacts should support lazy/deferred materialization.

Sources:

- https://buck2.build/docs/insights_and_knowledge/modern_dice/
- https://buck2.build/docs/users/advanced/deferred_materialization/
- https://buck2.build/docs/rule_authors/incremental_actions/

## SCIP / Sourcegraph — precise semantic code intelligence

Sourcegraph's precise code navigation uses SCIP, a language-agnostic semantic indexing protocol. SCIP indexes documents, symbol definitions and occurrences and supports compiler-derived navigation; Sourcegraph uses search-based navigation as a fallback when precise indexes are unavailable.

Skeleton implication: preserve evidence precision. Python AST and JS/TS lexical inference are useful fallbacks, but compiler/SCIP ingestion is the target for precise cross-reference edges. Never present lexical inference as compiler proof.

Sources:

- https://sourcegraph.com/docs/code-navigation/precise-code-navigation
- https://sourcegraph.com/docs/code-navigation/writing-an-indexer

## CycloneDX — component/dependency/supply-chain relationship graph

CycloneDX 1.7 models components, services, dependencies and relationships across software and other inventory types, including provenance/lifecycle metadata. CycloneDX 2.0 is being developed toward broader system transparency including threat and agent behavior information.

Skeleton implication: dependency and provenance nodes should be exportable into a validated CycloneDX representation instead of inventing an isolated security inventory format.

Sources:

- https://cyclonedx.org/specification/overview/
- https://cyclonedx.org/capabilities/sbom/
- https://cyclonedx.org/news/cyclonedx-v2.0-coming-soon/

## Skeleton's intended differentiator

These tools each solve important parts of the problem. Skeleton's index should connect layers that are usually separate:

**Git/content → symbols/imports → build DAG → reverse change impact → tests → security/supply-chain → game-creation capability evidence → agent batch ownership → release evidence.**

That combined graph is the target differentiator. It must be demonstrated with measured latency, cache-hit rate, precision/recall where applicable, test-selection quality, and release evidence before being described as superior in production.
