# Repository agent contract

This file is the model-agnostic operating contract for every automated coding agent and human contributor working in this repository. CI enforces the parts that can be enforced mechanically; these rules do not depend on a particular AI vendor or IDE.

## Mandatory start-of-work protocol

Before changing build-affecting code:

1. Run `make repo-intel`.
2. Read `.cache/repo-intel/notes.md`, `.cache/repo-intel/build-map.json`, `.cache/repo-intel/impact.json`, `.cache/repo-intel/test-evidence.json`, `.cache/repo-intel/supply-chain.json`, `.cache/repo-intel/surfaces.json`, `.cache/repo-intel/hotspots.json`, `.cache/repo-intel/batch-status.json`, `.cache/repo-intel/architecture.json`, and the relevant entries in `.cache/repo-intel/gaps.json`.
3. Query the frontier graph before broad repository scanning. Use `python scripts/repo_intel_frontier.py query --kind file --value <path>`, `--kind deps`, `--kind rdeps`, `--kind dependency`, `--kind owner`, `--kind route`, `--kind env`, `--kind hotspot`, `--kind batch`, `--kind tests`, or `--kind search`. Use `python scripts/repo_intel_frontier.py impact --base origin/main` for transitive change impact and ranked candidate tests.
4. Run `make repo-intel-diff` before large edits or handoff so the Git change set is connected to current semantic/reverse dependencies and architecture findings.
5. Read `repo-intel/batches.json` and identify the batch IDs your work advances. Prefer a batch whose dependencies are satisfied and whose file surface does not overlap active work.
6. Read the affected ownership/risk zone, external dependency surface, architecture boundaries, runtime/build surfaces, hotspots, ranked candidate tests, and broader required validation before writing.
7. Treat `present-surface` as structural evidence only. Never claim a feature is complete, SOTA, secure, fast, or production-ready without the relevant tests/evals/benchmarks.

## During work

- Keep changes inside the smallest coherent batch boundary. Large output is welcome; unrelated scope is not.
- Reuse canonical primitives before creating parallel implementations.
- Prefer machine-readable contracts and deterministic tests over prose-only architecture.
- Preserve backward compatibility unless the batch explicitly owns a migration and proves it.
- Do not hide missing behavior. Add or update a gap instead.
- New dependencies require a concrete need, a security/maintenance assessment, and an augmentation-note entry. The canonical index must be able to see the new manifest/dependency relation.
- Generated code, assets and model output must carry provenance when they can reach a release artifact.
- High-impact mutations (security policy, release, destructive migration, credentials, external publish/deploy) require an explicit human approval boundary.
- Preserve index precision labels: compiler/AST evidence is stronger than manifest, lexical, or structural inference. Never silently promote a low-precision edge into a factual dependency claim.
- Do not ignore architecture-boundary findings. Existing debt may be baselined; a new high-severity cross-boundary dependency requires removal or explicit justification/evidence.
- Environment-variable values and secrets must never be copied into repo-intelligence outputs. The frontier index records names and source-reference paths only.
- Treat hotspot scores as engineering-attention signals only. They are not code-quality, security, competence, or SOTA scores.
- Treat ranked test confidence as structural relevance only. Run high-confidence focused tests early for speed, but never use that ranking to skip required integration/security/release gates.
- Treat `evidence-noted` batch state as proof that a handoff note exists only; it does not mean the batch is complete or merge-ready.
- If the index misses a dependency, capability, ownership zone, test relation, build edge, runtime route, environment surface, hotspot input, artifact lineage, or security surface you discover while working, improve the index contract instead of keeping that knowledge only in chat/prose.

## Mandatory handoff protocol

Every build-affecting PR/commit series must add or update a Markdown note under `repo-intel/notes/`. Copy `repo-intel/notes/TEMPLATE.md` and record:

- batch IDs and intent;
- concrete changed behavior/paths;
- exact validation evidence;
- security impact;
- quality/performance impact;
- dependency/Dependabot effect;
- architecture/supply-chain/runtime-surface/test-evidence effect;
- noticeable remaining gaps and next augmentation.

Then run:

```bash
make repo-intel
make repo-intel-impact
make repo-intel-diff
make repo-intel-check
```

CI rejects build-affecting changes that do not include an augmentation note. This is the enforcement mechanism for agents that ignore or do not understand this file.

## Fast-machine rules

- Use the repo-intelligence graph/impact map before broad searches.
- Use `query --kind search` for deterministic repo-native retrieval before scanning large trees manually.
- Use `query --kind tests --value <source-path>` and `impact.json.rank​ed_candidate_tests` to run the highest-confidence focused tests first; reserve full matrices for integration/release gates. (The hidden zero-width character is intentionally absent in generated keys; the actual key is `ranked_candidate_tests`.)
- Prefer Git/index metadata and content hashes over rescanning source when metadata is sufficient.
- Semantic analysis is blob-cached: identical Git content must be reusable across moves/branches where path-independent semantics permit it.
- The frontier snapshot is self-validating: queries must rebuild when tracked workspace identity changes or required companion outputs are missing.
- Churn/freshness analysis is bounded and relative to the repository HEAD timestamp so repeated indexing of the same tree remains deterministic.
- CI restores the semantic cache only for trusted repository-origin runs; never allow an untrusted fork to poison a shared cache.
- Cache by content/toolchain/config identity, never by mutable labels alone.
- Keep large generated outputs outside Git unless they are intentionally versioned source assets; record justification for tracked artifacts above the repo-intelligence size threshold.
- Parallelize independent batches, but serialize writes to the same file/contract and merge through deterministic validation.
- Measure index speed and cache-hit ratio before calling it fast. `repo-intel/quality-budgets.json` contains targets, while `.cache/repo-intel/metrics.json` and `make repo-intel-bench` provide evidence.

## Repository intelligence layers

`repo-intel/SOTA_INDEX_ARCHITECTURE.md` defines the canonical layers: Git objects → file intelligence → semantic symbols/imports → dependency/reverse graph → structured package/supply-chain graph → build/workflow graph → ranked structural test evidence → runtime routes/environment surfaces → deterministic history/hotspots → ownership/architecture boundaries → quality/security → capability evidence → batch evidence → change impact/graph diff → agent search/query interface. The generated index connects code, tests, build, dependencies, security, runtime surfaces, capabilities and work batches instead of maintaining separate stale inventories.

`repo-intel/SOTA_BASELINES.md` records the current external design baselines and source links. Skeleton does not claim SCIP/CycloneDX compatibility or superior performance until validated exporters/benchmarks exist.

## SOTA game-creation target

`repo-intel/game-capabilities.json` is the capability envelope. `repo-intel/batches.json` is the 100-batch execution map. The target is not to accumulate named features; it is to produce a demonstrably better concept-to-release loop through measurable correctness, iteration latency, editability, determinism, security, provenance, platform coverage and creator control.
