# Repository agent contract

This file is the model-agnostic operating contract for every automated coding agent, bot, automation and human contributor working in this repository. CI enforces the parts that can be enforced mechanically; these rules do not depend on a particular AI vendor or IDE.

## Mandatory start-of-work protocol

Before changing build-affecting code:

1. Run `make repo-intel`.
2. Read `.cache/repo-intel/notes.md`, `.cache/repo-intel/build-map.json`, `.cache/repo-intel/impact.json`, `.cache/repo-intel/test-evidence.json`, `.cache/repo-intel/artifact-lineage.json`, `.cache/repo-intel/contributions.json`, `.cache/repo-intel/supply-chain.json`, `.cache/repo-intel/surfaces.json`, `.cache/repo-intel/hotspots.json`, `.cache/repo-intel/batch-status.json`, `.cache/repo-intel/architecture.json`, and the relevant entries in `.cache/repo-intel/gaps.json`.
3. Read `repo-intel/contributors.json` and identify the canonical actor IDs for every human, AI agent, bot, automation or orchestrator materially participating in the work. If an actor is new, register it before handoff rather than guessing an alias.
4. Query the frontier graph before broad repository scanning. Use `python scripts/repo_intel_frontier.py query --kind file --value <path>`, `--kind deps`, `--kind rdeps`, `--kind dependency`, `--kind owner`, `--kind route`, `--kind env`, `--kind hotspot`, `--kind batch`, `--kind tests`, `--kind artifact`, or `--kind search`. Use `python scripts/repo_intel_frontier.py impact --base origin/main` for transitive change impact, ranked candidate tests, and explicit affected artifacts.
5. Run `make repo-intel-diff` before large edits or handoff so the Git change set is connected to current semantic/reverse dependencies and architecture findings.
6. Read `repo-intel/batches.json` and identify the batch IDs your work advances. Prefer a batch whose dependencies are satisfied and whose file surface does not overlap active work.
7. Read the affected ownership/risk zone, external dependency surface, architecture boundaries, runtime/build surfaces, hotspots, ranked candidate tests, artifact lineage, contributor provenance, and broader required validation before writing.
8. Treat `present-surface` as structural evidence only. Never claim a feature is complete, SOTA, secure, fast, reproducible, or production-ready without the relevant tests/evals/benchmarks/attestations.

## During work

- Keep changes inside the smallest coherent batch boundary. Large output is welcome; unrelated scope is not.
- Reuse canonical primitives before creating parallel implementations.
- Prefer machine-readable contracts and deterministic tests over prose-only architecture.
- Preserve backward compatibility unless the batch explicitly owns a migration and proves it.
- Do not hide missing behavior. Add or update a gap instead.
- New dependencies require a concrete need, a security/maintenance assessment, and an augmentation-note entry. The canonical index must be able to see the new manifest/dependency relation.
- Generated code, assets and model output must carry provenance when they can reach a release artifact.
- High-impact mutations (security policy, release, destructive migration, credentials, external publish/deploy) require an explicit human approval boundary.
- Preserve index precision labels: compiler/AST evidence is stronger than manifest, lexical, structural, handoff-declared, or user-declared inference. Never silently promote a low-precision edge into a factual dependency or authorship claim.
- Do not ignore architecture-boundary findings. Existing debt may be baselined; a new high-severity cross-boundary dependency requires removal or explicit justification/evidence.
- Environment-variable values and secrets must never be copied into repo-intelligence outputs. The frontier index records names and source-reference paths only.
- Treat hotspot scores as engineering-attention signals only. They are not code-quality, security, competence, or SOTA scores.
- Treat ranked test confidence as structural relevance only. Run high-confidence focused tests early for speed, but never use that ranking to skip required integration/security/release gates.
- Treat artifact lineage as build-declaration evidence only. Do not infer arbitrary shell outputs, and do not equate a Docker/Compose lineage edge with a reproducible or signed release artifact.
- Treat `evidence-noted` batch state as proof that a handoff note exists only; it does not mean the batch is complete or merge-ready.
- Treat Git author/committer identity, explicit contribution trailers, handoff-note attribution, operational/tool surfaces, and owner-declared tooling as separate evidence classes. Never combine them into a single authorship claim.
- A connector/shared service identity does not prove which AI model contributed. When a human-owned Git identity lands AI-assisted work, preserve that participation in `**Author/agent:**` using canonical IDs.
- A branch/snapshot name such as `codex/...`, a model catalog entry, instruction file, or commit-message mention proves a repository surface/reference only. It is not direct authorship evidence.
- Squash merges, rebases, cherry-picks, imported histories and generated commits may collapse original Git attribution. Record material actors in the handoff note; do not reconstruct missing attribution by guesswork.
- When an orchestrator delegates to another bot/agent, record both if both materially contribute. Do not credit the executor to the orchestrator or vice versa without evidence.
- Unknown or newly introduced bots/models must be registered in `repo-intel/contributors.json` before handoff. The provenance gate fails explicit unregistered actor declarations.
- Never put raw contributor email addresses, credentials, tokens, prompt secrets, or private model configuration into generated provenance outputs or handoff notes.
- If the index misses a dependency, capability, ownership zone, test relation, build edge, runtime route, environment surface, hotspot input, artifact lineage, contributor identity/evidence class, or security surface you discover while working, improve the index contract instead of keeping that knowledge only in chat/prose.

## Mandatory handoff protocol

Every build-affecting PR/commit series must add or update a Markdown note under `repo-intel/notes/`. Copy `repo-intel/notes/TEMPLATE.md` and record:

- batch IDs and intent;
- canonical `Author/agent` actor IDs/aliases and contribution mode;
- concrete changed behavior/paths;
- exact validation evidence;
- security impact;
- quality/performance impact;
- dependency/Dependabot effect;
- architecture/supply-chain/runtime-surface/test-evidence/artifact-lineage effect;
- contribution/provenance edge cases such as shared connector identity, squash/rebase, generated commits, delegated bots or unknown model version;
- noticeable remaining gaps and next augmentation.

Then run:

```bash
make repo-intel
make repo-intel-impact
make repo-intel-diff
make repo-intel-check
```

CI rejects build-affecting changes that do not include an augmentation note and at least one canonical contributor/agent declaration. An explicitly named actor that is not registered fails closed. This is the enforcement mechanism for agents, bots or automations that ignore or do not understand this file.

## Fast-machine rules

- Use the repo-intelligence graph/impact map before broad searches.
- Use `query --kind search` for deterministic repo-native retrieval before scanning large trees manually.
- Use `query --kind tests --value <source-path>` and `impact.json` → `ranked_candidate_tests` to run the highest-confidence focused tests first; reserve full matrices for integration/release gates.
- Use `query --kind artifact` and `impact.json` → `affected_artifacts` before changing Dockerfiles, build contexts, packaging inputs, or release-adjacent source.
- Use `.cache/repo-intel/contributions.json` before attributing prior work or deciding whether a named AI/bot has direct, handoff-declared, operational-surface, or owner-declared evidence.
- Prefer Git/index metadata and content hashes over rescanning source when metadata is sufficient.
- Semantic analysis is blob-cached: identical Git content must be reusable across moves/branches where path-independent semantics permit it.
- Contribution history is bounded and does not attempt expensive blame reconstruction for every file during normal refresh.
- The frontier snapshot is self-validating: queries must rebuild when tracked workspace identity changes or required companion outputs are missing.
- Churn/freshness analysis is bounded and relative to the repository HEAD timestamp so repeated indexing of the same tree remains deterministic.
- CI restores the semantic cache only for trusted repository-origin runs; never allow an untrusted fork to poison a shared cache.
- Cache by content/toolchain/config identity, never by mutable labels alone.
- Keep large generated outputs outside Git unless they are intentionally versioned source assets; record justification for tracked artifacts above the repo-intelligence size threshold.
- Parallelize independent batches, but serialize writes to the same file/contract and merge through deterministic validation.
- Measure index speed and cache-hit ratio before calling it fast. `repo-intel/quality-budgets.json` contains targets, while `.cache/repo-intel/metrics.json` and `make repo-intel-bench` provide evidence.

## Repository intelligence layers

`repo-intel/SOTA_INDEX_ARCHITECTURE.md` defines the canonical layers: Git objects → file intelligence → semantic symbols/imports → dependency/reverse graph → structured package/supply-chain graph → build/workflow graph → ranked structural test evidence → explicit artifact lineage → contributor/agent/bot/automation provenance → runtime routes/environment surfaces → deterministic history/hotspots → ownership/architecture boundaries → quality/security → capability evidence → batch evidence → change impact/graph diff → agent search/query interface. The generated index connects code, tests, build, dependencies, artifacts, contributors, security, runtime surfaces, capabilities and work batches instead of maintaining separate stale inventories.

`repo-intel/SOTA_BASELINES.md` records the current external design baselines and source links. Skeleton does not claim SCIP/CycloneDX compatibility or superior performance until validated exporters/benchmarks exist.

## SOTA game-creation target

`repo-intel/game-capabilities.json` is the capability envelope. `repo-intel/batches.json` is the 100-batch execution map. The target is not to accumulate named features; it is to produce a demonstrably better concept-to-release loop through measurable correctness, iteration latency, editability, determinism, security, provenance, platform coverage and creator control.
