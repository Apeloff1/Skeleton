# Repository agent contract

This file is the model-agnostic operating contract for every automated coding agent and human contributor working in this repository. CI enforces the parts that can be enforced mechanically; these rules do not depend on a particular AI vendor or IDE.

## Mandatory start-of-work protocol

Before changing build-affecting code:

1. Run `make repo-intel`.
2. Read `.cache/repo-intel/notes.md`, `.cache/repo-intel/build-map.json`, `.cache/repo-intel/impact.json`, and the relevant entries in `.cache/repo-intel/gaps.json`.
3. Query the graph before broad repository scanning. Useful commands include `python scripts/repo_intel_sota.py query --kind file --value <path>`, `--kind deps`, `--kind rdeps`, and `python scripts/repo_intel_sota.py impact --base origin/main`.
4. Read `repo-intel/batches.json` and identify the batch IDs your work advances. Prefer a batch whose dependencies are satisfied and whose file surface does not overlap active work.
5. Read the affected ownership/risk zone and candidate tests from the impact report before writing.
6. Treat `present-surface` as structural evidence only. Never claim a feature is complete, SOTA, secure, fast, or production-ready without the relevant tests/evals/benchmarks.

## During work

- Keep changes inside the smallest coherent batch boundary. Large output is welcome; unrelated scope is not.
- Reuse canonical primitives before creating parallel implementations.
- Prefer machine-readable contracts and deterministic tests over prose-only architecture.
- Preserve backward compatibility unless the batch explicitly owns a migration and proves it.
- Do not hide missing behavior. Add or update a gap instead.
- New dependencies require a concrete need, a security/maintenance assessment, and an augmentation-note entry.
- Generated code, assets and model output must carry provenance when they can reach a release artifact.
- High-impact mutations (security policy, release, destructive migration, credentials, external publish/deploy) require an explicit human approval boundary.
- Preserve index precision labels: compiler/AST evidence is stronger than lexical/structural inference. Never silently promote a low-precision edge into a factual dependency claim.
- If the index misses a dependency, capability, ownership zone, or test relation you discover while working, improve the index contract instead of keeping that knowledge only in chat/prose.

## Mandatory handoff protocol

Every build-affecting PR/commit series must add or update a Markdown note under `repo-intel/notes/`. Copy `repo-intel/notes/TEMPLATE.md` and record:

- batch IDs and intent;
- concrete changed behavior/paths;
- exact validation evidence;
- security impact;
- quality/performance impact;
- dependency/Dependabot effect;
- noticeable remaining gaps and next augmentation.

Then run:

```bash
make repo-intel
make repo-intel-impact
make repo-intel-check
```

CI rejects build-affecting changes that do not include an augmentation note. This is the enforcement mechanism for agents that ignore or do not understand this file.

## Fast-machine rules

- Use the repo-intelligence graph/impact map before broad searches.
- Use reverse dependencies and candidate tests to narrow validation; reserve full matrices for integration/release gates.
- Prefer Git/index metadata and content hashes over rescanning source when metadata is sufficient.
- Semantic analysis is blob-cached: identical Git content must be reusable across moves/branches where path-independent semantics permit it.
- Cache by content/toolchain/config identity, never by mutable labels alone.
- Keep large generated outputs outside Git unless they are intentionally versioned source assets; record justification for tracked artifacts above the repo-intelligence size threshold.
- Parallelize independent batches, but serialize writes to the same file/contract and merge through deterministic validation.
- Measure index speed and cache-hit ratio before calling it fast. `repo-intel/quality-budgets.json` contains targets, while `.cache/repo-intel/metrics.json` contains evidence.

## Repository intelligence layers

`repo-intel/SOTA_INDEX_ARCHITECTURE.md` defines the canonical layers: Git objects → file intelligence → semantic symbols/imports → dependency/reverse graph → build graph → quality/security → capability evidence → change impact → query/agent interface. The generated index connects code, tests, build, security, capabilities and work batches instead of maintaining separate stale inventories.

## SOTA game-creation target

`repo-intel/game-capabilities.json` is the capability envelope. `repo-intel/batches.json` is the 100-batch execution map. The target is not to accumulate named features; it is to produce a demonstrably better concept-to-release loop through measurable correctness, iteration latency, editability, determinism, security, provenance, platform coverage and creator control.
