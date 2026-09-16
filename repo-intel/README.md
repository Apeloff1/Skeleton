# Repository intelligence

Skeleton's repository index is a **content-addressed build knowledge graph plus contribution-provenance ledger**, not a generated directory listing. The authoritative code/build interface is `scripts/repo_intel_frontier.py`; contributor/agent evidence is produced by `scripts/repo_intel_contributions.py`. Local and CI entry points compose both through the Make targets below.

## Fast path

```bash
make repo-intel
make repo-intel-contributions
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
python scripts/repo_intel_frontier.py query --kind tests --value skeleton/genesis.py
python scripts/repo_intel_frontier.py query --kind artifact --value backend
python scripts/repo_intel_frontier.py query --kind search --value "game mechanics deterministic"
```

## Generated working set

`.cache/repo-intel/` is disposable generated state. Important outputs include:

- `index.json` — schema-v5 file intelligence, semantics, history, centrality and graph metadata;
- `graph.json` / `symbols.json` — typed graph and symbol records;
- `build-map.json` / `build-relationships.json` — entry points, workflows, package scripts, Make targets and repository-file relationships;
- `supply-chain.json` / `dependencies.json` — canonical external components plus direct build-facing declaration inventory;
- `surfaces.json` — HTTP/Expo route discovery and environment-variable **names/reference paths only**;
- `test-evidence.json` — structural source→test evidence and focused-test ranking inputs;
- `artifact-lineage.json` — explicit Docker/Compose build artifact inputs, stages and service lineage without arbitrary shell-output inference;
- `contributions.json` — bounded Git identities, explicit contribution trailers, handoff-note declarations, AI/bot/automation surfaces, unknown identities and evidence-class semantics;
- `impact.json` / `change-set.json` / `graph-diff.json` — current change and reverse-impact evidence, ranked tests and affected explicit artifacts;
- `hotspots.json` / `history.json` — bounded deterministic churn, centrality and relative engineering-attention signals;
- `batch-status.json` — 100-batch plan with conservative handoff-note evidence state;
- `search-catalog.json` — compact deterministic agent retrieval records;
- `gaps.json`, `security-quality.json`, `architecture.json`, `codeowners.json` — capability, security, boundary and ownership evidence;
- `metrics.json`, `notes.md`, `dependabot-notes.md` — measured health and human-facing augmentation notes;
- `semantic-cache.json` — Git-blob-keyed semantic cache.

Generated outputs are ignored cache material; contracts live under `repo-intel/` and are reviewed source.

## Evidence precision

The index never collapses different evidence strengths into one claim:

- Python symbols/imports: AST-derived;
- JS/TS symbols/imports: conservative lexical evidence until validated compiler/SCIP ingestion lands;
- supported dependency manifests: structured parser evidence;
- workflow/build links: lexical references to tracked paths/modules/targets;
- test ranking: structural relevance evidence, not proof that broader gates can be skipped;
- artifact lineage: explicit Docker/Compose declaration evidence, not proof of reproducible/signed release output;
- routes: structural discoverability, not runtime reachability proof;
- CODEOWNERS: approximate local matching, while GitHub remains authoritative;
- capability `present-surface`: discoverable implementation evidence only;
- Git author/committer or explicit direct-contribution trailer: direct Git contribution evidence;
- `Author/agent` augmentation-note declaration: explicit handoff participation evidence;
- instruction/workflow/branch/path/message reference: operational-surface evidence only;
- owner-declared AI/tool registry entry: known workflow/tooling context, not per-commit authorship.

No file/path match, hotspot score, batch note, tool mention, branch name, dependency declaration or AI name by itself proves correctness, security, production readiness, completion, SOTA quality, or authorship.

## Contribution provenance

`repo-intel/contributors.json` is the canonical identity/evidence registry. It currently accounts for repository-observed or owner-declared humans, AI agents, dependency bots, CI automations, orchestrators and AI platforms. The generated ledger intentionally handles these edge cases:

- **shared connector identity:** a commit authored by the repository account is not automatically credited to an AI; use a canonical `Author/agent` handoff declaration or explicit Git trailer;
- **squash/rebase/cherry-pick/imported history:** only observable Git and handoff evidence is reported; missing attribution is never reconstructed by guesswork;
- **delegated bot chains:** orchestrator and executor remain separate actors unless explicit evidence links both to the work;
- **unknown bots/models:** stable hashed unknown identities are retained, and explicitly named unregistered actors fail the handoff gate;
- **model versions:** a vendor/tool identity does not imply a model/version; version claims require explicit evidence;
- **surface-only evidence:** instruction files, model catalogs, branch/snapshot names and commit-message references do not become authorship claims;
- **privacy:** generated provenance does not emit raw contributor email addresses or secrets.

`make repo-intel-check` runs both the ordinary augmentation-note gate and the canonical contributor-provenance gate.

## Agent/update contract

`AGENTS.md` is the model-neutral contract. Before build-affecting changes, humans, agents, bots and automations refresh the index, inspect impact and read `contributions.json`. During work they improve missing index knowledge rather than leaving it only in chat. Before handoff they add/update a note in `repo-intel/notes/`, name canonical actors, and run the Make sequence above.

The required Merge Readiness quality/security job runs the frontier snapshot, contribution snapshot, augmentation-note gate and contributor-provenance gate, so this is enforced independently of whether a particular model follows prompt instructions.

## Security and dependencies

The core index and provenance layer are Python-standard-library only and network-free. Environment-variable values and raw contributor emails are never emitted. Offline dependency inventory is intentionally direct-declaration evidence; GitHub Dependency Graph, Dependabot, dependency review, CodeQL, secret scanning, Gitleaks, and the repository's other security workflows remain authoritative for resolved/transitive vulnerability and platform security state.

## Architecture and roadmap

- `SOTA_INDEX_ARCHITECTURE.md` — frontier-v5 layers, implemented surfaces and remaining precision/scale work.
- `SOTA_BASELINES.md` — external design baselines and evidence discipline.
- `query-contract.json` — supported graph/retrieval vocabulary and precision semantics.
- `deep-index-contract.json` — deterministic history, surfaces, hotspot, batch and search rules.
- `contributors.json` — canonical actor identities plus direct/handoff/surface/user-declared evidence semantics.
- `test-evidence-contract.json` — focused test-selection evidence rules.
- `artifact-lineage-contract.json` — explicit build-artifact lineage rules.
- `quality-budgets.json` / `telemetry-contract.json` — targets and required measured evidence.
- `game-capabilities.json` — game-creation capability envelope.
- `batches.json` — exactly 100 dependency-aware work batches.

The remaining major index evolutions are validated SCIP/compiler ingestion, historical test outcome ranking, hermetic action fingerprints/remote cache execution, persisted base graph snapshots, validated SPDX/CycloneDX export with transitive correlation, signed release attestations, route/auth runtime evidence, per-file contribution lineage, GitHub PR/review provenance correlation, and scalable graph/cache sharding.
