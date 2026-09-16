# Build augmentation note — B001 repository intelligence spine

- **Batch IDs:** B001, B002, B005, B006, B071, B081, B091
- **Area:** repository layout, semantic/build intelligence, impact analysis, agent handoff, dependency/security visibility
- **Author/agent:** ChatGPT
- **Intent:** Evolve ad-hoc repository discovery into a content-addressed repository knowledge graph that can guide agents, tests, security review, build selection, and later distributed execution.

## What changed

The original Git-index file inventory has been substantially augmented with a new stdlib-only semantic graph layer in `scripts/repo_intel_sota.py`. The canonical `make repo-intel` path now builds that richer index.

The generated snapshot now targets these layers:

1. Git object/path/blob/size metadata.
2. File language, role, subsystem, ownership/risk zone, test/build/security/generated flags.
3. Blob-cached semantic records: Python AST symbols/imports/tests and conservative JS/TS symbols/imports with explicit precision labels.
4. Typed forward and reverse graph edges for containment, imports, tests and ownership.
5. Dependency-cycle detection.
6. Build topology: manifests, workflows, tests, entrypoints and hot subsystems.
7. Capability/gap and security/quality reports.
8. Reverse-dependency change impact with affected files, subsystems, candidate tests, workflows, high-risk zones and capability evidence.
9. Machine queries for files, symbols, dependencies, reverse dependencies and subsystems.
10. Measured index telemetry plus explicit performance/quality budgets.

New source contracts under `repo-intel/` define graph semantics, ownership zones, query vocabulary, snapshot schema, precision levels, evidence levels, telemetry, quality budgets, and interoperability direction. `SOTA_INDEX_ARCHITECTURE.md` documents the complete graph architecture.

## SOTA design grounding

The design intentionally adopts proven concepts from large-scale tooling rather than inventing another flat manifest:

- build dependency/reverse-dependency DAGs and content-addressable build concepts;
- incremental invalidation and reuse of unchanged content;
- precise semantic-index concepts (definitions/symbols/references) with explicit fallback precision;
- supply-chain component/dependency/provenance modeling;
- one additional Skeleton-specific layer connecting code → build → tests → security → game capability → work batch → release evidence.

The repo does **not** claim external SCIP or CycloneDX compatibility yet. `export-contract.json` explicitly marks those exporters as future compatibility layers that must validate against the external formats before being advertised.

## Validation evidence

Added `tests/test_repo_intel_sota.py` covering:

- Python AST symbol/import/test extraction;
- explicit syntax-parse failure reporting;
- JS/TS lexical import/export precision;
- local Python and JS/TS dependency resolution;
- reverse-edge precision preservation;
- strongly connected dependency-cycle detection;
- most-specific ownership-zone selection;
- transitive reverse change impact and candidate-test surfacing;
- presence/validity of extended repo-intelligence contracts;
- measurable-budget semantics and bidirectional query contract.

The dedicated Repository Intelligence workflow now compiles both indexers, runs the original and new focused regression files, generates the semantic graph, runs the augmentation gate, queries Dependabot data when permissions allow, and publishes graph/impact/cache/ownership metrics.

## Security impact

The index now marks security-sensitive files and high/critical ownership zones so impact reports expose when a change reaches build/security boundaries. It retains static detection of Dependabot, CodeQL, dependency review/security, secret scanning and Gitleaks controls, while CI optionally enriches the report with live Dependabot alert/PR data.

The tracked `backend/godot` binary (roughly 103 MB in the current tree) remains an explicit repository-performance and supply-chain review point. This batch still does not move it without measurement; B006/B091 own the verified distribution/embedding decision.

No new runtime or third-party indexing dependency was added. The semantic graph is Python 3.11 stdlib-only, reducing index supply-chain risk.

## Quality/performance impact

Semantic analysis is now cached by Git blob SHA. Identical clean content can reuse its semantic record instead of being reparsed. The graph materializes reverse edges once, making impact queries graph traversals rather than repeated repository scans.

Precision is explicit: Python relations are AST-derived; current JS/TS relations are conservative lexical evidence. Lower-precision relationships may widen an impact set but may not be silently presented as compiler-proven.

`quality-budgets.json` defines engineering targets (warm refresh, impact latency, cache-hit ratio, parse success, ownership coverage). `telemetry-contract.json` defines the measurements required before any speed/quality claim. These are targets, not achieved-performance claims.

## Dependabot/dependency note

No third-party dependency is introduced. Existing Dependabot ecosystems remain GitHub Actions, Python, npm and Docker. The index consumes dependency/security state; it does not replace Dependabot or vulnerability scanning.

## Noticeable gaps / next augmentation

The index is now materially deeper, but the following are deliberate next steps rather than hidden gaps:

- ingest compiler/SCIP indexes when available for precise Python/TypeScript references across the full graph;
- persist semantic cache across CI runners with a pinned/verified cache mechanism;
- parse structured package manifests into external dependency nodes/edges and export CycloneDX-compatible BOM data;
- ingest CODEOWNERS/human ownership in addition to architectural zones;
- learn/select tests from historical execution evidence, not only graph candidates;
- add action fingerprints, declared inputs/outputs and remote execution/cache compatibility;
- add graph diff between commits/branches for review agents;
- link benchmarks/release evidence directly to capability nodes;
- measure full/warm snapshot latency and cache-hit ratio on representative repo sizes;
- resolve/measure import cycles and architecture-boundary violations rather than treating all cycles equally.

Game-creation gaps remain tracked separately in `game-capabilities.json` / the 100-batch graph. The repository index is now designed to expose and route those gaps rather than certify them from path names.

## Build handoff

- [x] Git/content-addressed base index
- [x] semantic symbols/imports with precision labels
- [x] forward + reverse typed graph
- [x] ownership/risk zones
- [x] dependency-cycle discovery
- [x] reverse change-impact analysis
- [x] candidate-test/workflow/security-zone impact output
- [x] query interface
- [x] measurable telemetry/budget contracts
- [x] focused graph/index regressions
- [x] dedicated CI workflow updated for the rich index
- [ ] current-head CI execution completed successfully
- [ ] measured warm/full index benchmark evidence
- [ ] compiler/SCIP ingestion
- [ ] CycloneDX exporter validation
- [ ] B006/B091 decision on tracked Godot binary
