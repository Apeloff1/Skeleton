# SOTA repository intelligence architecture

This document defines the target architecture for the Skeleton repository index. The index is not a directory listing. It is a content-addressed repository knowledge graph used by humans, agents, CI, security automation, build orchestration, and future distributed execution.

## Design goals

1. **Incremental by default.** Reuse Git blob identities and cache semantic analysis by blob hash. A clean file should require metadata lookup, not reparsing.
2. **Graph-first.** Model files, symbols, packages, tests, workflows, build manifests, capabilities, security controls, and generated artifacts as typed nodes connected by typed edges.
3. **Bidirectional impact.** Every dependency edge should support reverse traversal so a change can answer: what code, tests, workflows, build targets, capabilities, and release surfaces are affected?
4. **Precise when available, graceful when not.** Prefer AST/compiler-derived structure. Fall back to conservative lexical relationships rather than silently pretending precision.
5. **Content addressed.** Semantic records are keyed by Git blob SHA so identical content is analyzed once even if paths move or branches converge.
6. **Build-facing.** The index must expose declared inputs/outputs, entry points, manifests, workflows, caches, large artifacts, critical paths, and change impact.
7. **Security-facing.** The same graph must expose sensitive zones, dependency manifests, supply-chain controls, oversized artifacts, ownership gaps, and generated-code/tool boundaries.
8. **Agent-facing.** Agents read the current index before work, claim batches, append handoff notes, and update the index before handoff. CI enforces the protocol.
9. **Evidence-first.** Structural discovery is not proof of correctness, production readiness, or SOTA quality. Capability claims require tests/evals/benchmarks linked into the graph.
10. **Interoperable.** Keep exports close to established concepts: SCIP-like symbols/occurrences, build DAGs with reverse dependencies, and CycloneDX-style component/dependency relationships.

## Index layers

### L0 — Git object layer

Source of truth for tracked path, mode, blob SHA, working-tree dirtiness, byte size, and repository digest.

### L1 — File intelligence

Per-file language, role, subsystem, owner zone, test/generated/security/build flags, manifest classification, and semantic cache key.

### L2 — Semantic code layer

Top-level and nested symbols where cheaply extractable, imports, local module references, exported names, and test definitions. Python uses the standard-library AST. JS/TS use conservative import/export extraction until a compiler/SCIP indexer is integrated.

### L3 — Dependency graph

Typed edges include `imports`, `tests`, `declares`, `contains`, `workflow-uses`, `depends-on`, `builds`, and `evidence-for`. Reverse edges are generated for fast impact analysis.

### L4 — Build graph

Entry points, dependency manifests, package scripts, containers, workflows, build/test commands, large artifacts, generated outputs, and future remote-cache/action keys.

### L5 — Quality and security graph

Test coverage surface, ownership gaps, cycle findings, large/opaque artifacts, dependency update coverage, workflow/security controls, provenance hooks, and security-sensitive zones.

### L6 — Capability/evidence graph

Game-creation capabilities link to structural anchors, tests, benchmarks, security constraints, and batch IDs. `present-surface` means discoverable implementation evidence only. Competitive/SOTA status requires explicit eval evidence.

### L7 — Change-impact graph

Given a Git base or explicit file set, compute direct and transitive reverse dependencies, impacted subsystems, candidate tests, workflows, security zones, and capability records.

### L8 — Query/agent interface

Machine commands expose `snapshot`, `query`, `impact`, `doctor`, `check`, `gate`, and Dependabot-note generation. Outputs are deterministic JSON plus compact Markdown notes.

## Performance architecture

The index follows three proven large-scale ideas:

- **Git-backed content addressing:** clean content reuses blob SHA instead of being rehashed.
- **Incremental invalidation:** semantic records are cached per blob and only dirty/new blobs are reparsed; reverse dependency traversal limits downstream recomputation.
- **Deferred detail:** expensive semantic work is only performed for supported source files; opaque assets/binaries remain metadata-only until a specialized indexer is requested.

Target budgets are engineering goals, not claims until measured in CI telemetry:

- warm metadata refresh: sub-second for ordinary changes;
- changed-source semantic refresh: proportional to changed blobs, not repository size;
- impact query: graph traversal only after snapshot generation;
- deterministic output for the same tree/config;
- no network dependency for the core indexer.

## SOTA parity and beyond

The architecture intentionally combines capabilities that are commonly split across tools:

- build-system dependency/reverse-dependency graphs and content-addressable caching;
- precise-code-index concepts such as symbols, occurrences, definitions, and references;
- software-supply-chain component/dependency relationships;
- agent handoff state, capability gaps, security notes, and product-roadmap evidence.

Skeleton should go beyond baseline repository indexing by connecting **code → build → tests → security → game capability → agent work batch → release evidence** in one graph.

## Required next evolutions

1. Persist blob-keyed semantic cache and incremental graph fragments.
2. Add compiler/SCIP ingestion when indexers are available, while keeping AST fallback.
3. Add dependency cycle detection and architecture-boundary violations.
4. Add test selection ranking from reverse dependencies plus historical test evidence.
5. Add action/build fingerprints for remote-cache compatibility.
6. Export CycloneDX-compatible component/dependency data and provenance links.
7. Add benchmark telemetry for index latency, cache-hit rate, graph size, and impact-query latency.
8. Add ownership and CODEOWNERS ingestion.
9. Add generated artifact lineage and release-evidence nodes.
10. Add graph-diff summaries between branches/commits for AI agents and review automation.
