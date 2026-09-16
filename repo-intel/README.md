# Repository intelligence

Skeleton's repository index is a **content-addressed build knowledge graph**, not a generated directory listing. The authoritative interface is `scripts/repo_intel_frontier.py`; local and CI entry points call it through the Make targets below.

## Fast path

```bash
make repo-intel
make repo-intel-impact
make repo-intel-diff
make repo-intel-doctor
make repo-intel-check
make repo-intel-bench
```

Agents should query before broad scans:

```bash
python scripts/repo_intel_frontier.py query --kind file --value skeleton/genesis.py
python scripts/repo_intel_frontier.py query --kind deps --value skeleton/genesis.py --transitive
python scripts/repo_intel_frontier.py query --kind rdeps --value skeleton/kernel/event_bus.py --transitive
python scripts/repo_intel_frontier.py query --kind dependency --value fastapi
python scripts/repo_intel_frontier.py query --kind route --value /api
python scripts/repo_intel_frontier.py query --kind env --value API
python scripts/repo_intel_frontier.py query --kind hotspot --value gameforge
python scripts/repo_intel_frontier.py query --kind batch --value B021
python scripts/repo_intel_frontier.py query --kind search --value "game mechanics deterministic"
```

## Generated working set

`.cache/repo-intel/` is disposable generated state. Important outputs include:

- `index.json` — schema-v5 file intelligence, semantics, history, centrality and graph metadata;
- `graph.json` / `symbols.json` — typed graph and symbol records;
- `build-map.json` / `build-relationships.json` — entry points, workflows, package scripts, Make targets and repository-file relationships;
- `supply-chain.json` / `dependencies.json` — canonical external components plus direct build-facing declaration inventory;
- `surfaces.json` — HTTP/Expo route discovery and environment-variable **names/reference paths only**;
- `impact.json` / `change-set.json` / `graph-diff.json` — current change and reverse-impact evidence;
- `hotspots.json` / `history.json` — bounded deterministic churn, centrality and relative engineering-attention signals;
- `batch-status.json` — 100-batch plan with conservative handoff-note evidence state;
- `search-catalog.json` — compact deterministic agent retrieval records;
- `gaps.json`, `security-quality.json`, `architecture.json`, `codeowners.json` — capability, security, boundary and ownership evidence;
- `metrics.json`, `notes.md`, `dependabot-notes.md` — measured health and human-facing augmentation notes;
- `semantic-cache.json` — Git-blob-keyed semantic cache.

Generated outputs are ignored cache material; contracts live under `repo-intel/` and are reviewed source.

## Evidence precision

The graph never collapses different evidence strengths into one claim:

- Python symbols/imports: AST-derived;
- JS/TS symbols/imports: conservative lexical evidence until validated compiler/SCIP ingestion lands;
- supported dependency manifests: structured parser evidence;
- workflow/build links: lexical references to tracked paths/modules/targets;
- routes: structural discoverability, not runtime reachability proof;
- CODEOWNERS: approximate local matching, while GitHub remains authoritative;
- capability `present-surface`: discoverable implementation evidence only.

No file/path match, hotspot score, batch note, or dependency declaration by itself proves correctness, security, production readiness, completion, or SOTA quality.

## Agent/update contract

`AGENTS.md` is the model-neutral contract. Before build-affecting changes, agents refresh the index and inspect impact. During work they improve missing index knowledge rather than leaving it only in chat. Before handoff they add/update a note in `repo-intel/notes/` and run the Make sequence above.

The required Merge Readiness quality/security job runs the frontier snapshot and augmentation-note gate, so this is enforced independently of whether a particular model follows prompt instructions.

## Security and dependencies

The core index is Python-standard-library only and network-free. Environment-variable values are never emitted. Offline dependency inventory is intentionally direct-declaration evidence; GitHub Dependency Graph, Dependabot, dependency review, CodeQL, secret scanning, Gitleaks, and the repository's other security workflows remain authoritative for resolved/transitive vulnerability and platform security state.

## Architecture and roadmap

- `SOTA_INDEX_ARCHITECTURE.md` — frontier-v5 layers, implemented surfaces and remaining precision/scale work.
- `SOTA_BASELINES.md` — external design baselines and evidence discipline.
- `query-contract.json` — supported graph/retrieval vocabulary and precision semantics.
- `deep-index-contract.json` — deterministic history, surfaces, hotspot, batch and search rules.
- `quality-budgets.json` / `telemetry-contract.json` — targets and required measured evidence.
- `game-capabilities.json` — game-creation capability envelope.
- `batches.json` — exactly 100 dependency-aware work batches.

The remaining major index evolutions are validated SCIP/compiler ingestion, historical test ranking, hermetic action fingerprints/remote cache execution, persisted base graph snapshots, validated SPDX/CycloneDX export with transitive correlation, release artifact lineage, route/auth runtime evidence, and scalable graph/cache sharding.
