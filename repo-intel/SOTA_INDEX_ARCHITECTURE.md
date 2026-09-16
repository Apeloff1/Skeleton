# SOTA repository intelligence architecture

This document defines the target and implemented architecture for the Skeleton repository index. The index is not a directory listing. It is a content-addressed repository knowledge graph used by humans, agents, CI, security automation, build orchestration, and future distributed execution.

## Design goals

1. **Incremental by default.** Reuse Git blob identities and cache semantic analysis by blob hash. A clean file should require metadata lookup, not reparsing.
2. **Graph-first.** Model files, symbols, packages, tests, workflows, build targets, capabilities, security controls, runtime surfaces, work batches, and generated artifacts as typed nodes/records connected by typed evidence.
3. **Bidirectional impact.** Every dependency/build edge should support reverse traversal so a change can answer: what code, tests, workflows, build targets, dependencies, capabilities, security zones, and release surfaces are affected?
4. **Precise when available, graceful when not.** Prefer AST/compiler-derived structure. Fall back to conservative lexical relationships and label the precision instead of pretending certainty.
5. **Content addressed.** Semantic records are keyed by Git blob SHA so identical content is analyzed once even if paths move or branches converge.
6. **Build-facing.** Expose entry points, manifests, package scripts, Make targets, workflows, large artifacts, runtime surfaces, caches, hotspots, and change impact.
7. **Security-facing.** Expose sensitive zones, dependency declarations, supply-chain controls, oversized artifacts, ownership gaps, environment-variable names, generated-code/tool boundaries, and architecture findings without copying secret values.
8. **Agent-facing.** Agents read the current index before work, query before broad scans, claim batches, append handoff notes, and update the index before handoff. CI enforces the protocol.
9. **Evidence-first.** Structural discovery is not proof of correctness, production readiness, security, or SOTA quality. Capability claims require tests/evals/benchmarks linked to the relevant surface.
10. **Interoperable.** Keep exports close to established concepts: SCIP-like symbols/occurrences, build DAGs with reverse dependencies, and CycloneDX/SPDX-style component/dependency relationships.

## Frontier v5 layers

### L0 — Git object layer

Tracked path, mode, Git blob SHA, working-tree dirtiness, byte size, repository digest, and bounded Git-history metadata. History age is relative to HEAD commit time so the same tree stays deterministic.

### L1 — File intelligence

Per-file language, role, subsystem, owner/risk zone, test/generated/security/build flags, manifest classification, semantic cache key, bounded churn, centrality, and relative hotspot score.

### L2 — Semantic code layer

Top-level and nested symbols, imports/local module references, exported names, and test definitions. Python uses the standard-library AST. JS/TS currently use conservative lexical import/export extraction until compiler/SCIP ingestion is validated.

### L3 — Typed dependency / reverse graph

Edges include `imports`, `tests`, `declares-dependency`, `workflow-uses`, `build-uses`, `declares-target`, `invokes`, `contains`, and `owned-by`. Reverse edges are generated for fast impact traversal.

### L4 — Structured supply-chain graph

Python/npm manifests, Docker base images, and GitHub Actions declarations become structured external-dependency evidence. CODEOWNERS and architecture-boundary analysis remain separate but connected views. Offline declarations do **not** claim transitive resolution or vulnerability state; GitHub Dependency Graph/Dependabot remains authoritative for that evidence.

### L5 — Build / workflow graph

Make targets, package scripts, workflows, referenced repository scripts/files, entry points, containers, tests, manifests, and generated outputs. This is the substrate for future hermetic action fingerprints and remote-cache scheduling.

### L6 — Runtime / creator surfaces

FastAPI-style HTTP decorator routes, Expo file routes, and environment-variable **names/reference paths only**. Values are never emitted. These are discoverability surfaces, not runtime reachability or authorization proof.

### L7 — Deterministic history / hotspots

A bounded Git window contributes touches/freshness. Combined with fan-in/fan-out, size, ownership risk, and security sensitivity, the index emits a relative engineering-attention signal. Hotspot scores are explicitly **not** quality, security, competence, or SOTA grades.

### L8 — Quality / security graph

Test surface, ownership gaps, cycles, large/opaque artifacts, dependency-update coverage, workflow/security controls, provenance hooks, architecture findings, and security-sensitive zones.

### L9 — Capability / batch evidence graph

Game-creation capabilities link to structural anchors and build notes. The 100-batch plan exposes `planned` and `evidence-noted`; the latter means only that a tracked handoff note references the batch. It does not mean complete or merge-ready.

### L10 — Change-impact / graph diff

Given a Git base or explicit file set, compute direct/transitive reverse dependencies, impacted subsystems, candidate tests, workflows, external dependency declarations, security zones, and architecture findings. Current graph diff combines Git path status with current-head semantics; exact deleted-edge comparison remains a future base-snapshot feature.

### L11 — Agent retrieval / query interface

Machine commands expose `snapshot`, `query`, `impact`, `diff`, `doctor`, `check`, `gate`, and Dependabot-note generation. Deterministic lexical search spans paths, symbols, imports, routes, env names, package declarations, and subsystems without requiring a network embedding service.

## Performance architecture

The index follows three large-scale ideas:

- **Git-backed content addressing:** clean semantic content reuses blob SHA rather than being rehashed/reparsed.
- **Incremental invalidation:** semantic records are cached by blob and only new/dirty content is reparsed; reverse dependency traversal narrows impact work.
- **Deferred detail:** expensive semantic work is only performed where supported; opaque assets/binaries remain metadata-only until a specialized indexer is requested.

Targets in `quality-budgets.json` are engineering goals, not claims. `make repo-intel-bench` measures the **frontier v5** path and records cold/warm wall time, cache reuse, graph size, dependencies, routes, build targets, search-document count, and history window.

## Implemented in frontier v5

- Git object / tracked-file index and repository digest;
- blob-keyed semantic cache;
- Python AST symbols/imports and lexical JS/TS fallback;
- forward/reverse graph and cycle detection;
- structured direct supply-chain declarations;
- CODEOWNERS approximation and architecture-boundary findings;
- workflow-to-file and Make-target relationships;
- route and env-name/reference discovery;
- deterministic bounded churn/freshness and hotspot records;
- capability/gap map and 100-batch evidence state;
- reverse impact and Git path-status graph diff;
- deterministic agent search catalog;
- Dependabot/security notes and required augmentation-note enforcement;
- required Merge Readiness integration and cold/warm benchmark path.

## Remaining precision / scale evolutions

1. **Compiler/SCIP ingestion.** Add validated JS/TS and multi-language compiler index ingestion while retaining AST/lexical fallback and explicit evidence precision.
2. **Historical test evidence.** Rank candidate tests using runtime, pass/fail, flake, mutation, and coverage evidence rather than dependency proximity alone.
3. **Hermetic action fingerprints.** Model toolchain/config/input/output identities for true content-addressable local/remote build execution.
4. **Persisted base graph snapshots.** Diff semantic edges/nodes across refs, including deleted files/relationships, without inferring historical state from the current graph.
5. **Validated SBOM export.** Produce CycloneDX/SPDX exports with lockfile/transitive correlation and provenance, then compare them against GitHub Dependency Graph evidence.
6. **Artifact lineage.** Connect generated assets/binaries to exact source/tool/model/input/output fingerprints and release evidence.
7. **Route/auth evidence.** Link discovered routes to runtime reachability, authorization tests, schemas, handlers, rate limits, and integration evidence.
8. **Distributed graph/cache shards.** Shard graph fragments and content caches when repository scale makes single-process JSON the limiting factor.
9. **Calibrated hotspot policy.** Validate hotspot weights against measured build regressions, review defects, ownership gaps, and incident evidence before using them for automatic prioritization.
10. **Signed batch completion ledger.** Keep `evidence-noted` conservative until completion can be backed by required tests/evals, dependency satisfaction, review/merge identity, and release evidence.

## SOTA discipline

The index should go beyond ordinary code search by connecting **code → build → tests → supply chain → security → runtime surfaces → game capability → agent work batch → release evidence** in one queryable graph. “SOTA” remains a target architecture and measured comparison, never a self-awarded label. New layers must preserve deterministic output, evidence precision, low incremental cost, and explicit non-claims.
