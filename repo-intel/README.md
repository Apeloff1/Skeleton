# Repository intelligence

`repo-intel/` is the source configuration and policy for Skeleton's repository knowledge graph. Generated state lives under `.cache/repo-intel/` and is rebuilt from Git plus these contracts.

## Commands

```bash
make repo-intel          # validate + generate machine/human snapshot
make repo-intel-check    # validate contracts + require augmentation note for build changes
python scripts/repo_intel.py impact --base origin/main
python scripts/repo_intel.py query --kind file --value skeleton/genesis.py
python scripts/repo_intel.py doctor
```

## Source contracts

- `config.json` — subsystems, entrypoints, build-affecting surfaces and thresholds.
- `batches.json` — exactly 100 dependency-aware program batches.
- `game-capabilities.json` — capability/evidence envelope for SOTA game creation.
- `ownership.json` — architectural ownership/risk zones.
- `query-contract.json` — supported machine query vocabulary.
- `index-schema.json` — generated snapshot schema contract.
- `graph-semantics.md` — node/edge direction, precision and evidence semantics.
- `quality-budgets.json` — measurable performance/quality targets.
- `telemetry-contract.json` — metrics required before performance claims.
- `export-contract.json` — SCIP/CycloneDX/build-graph interoperability direction.
- `SOTA_INDEX_ARCHITECTURE.md` — architecture and evolution rationale.
- `notes/` — append-only build/agent handoff evidence.

## Generated state

The target generated surface is:

- `index.json` — enriched file + semantic + graph snapshot.
- `graph.json` — typed forward/reverse dependency graph.
- `symbols.json` — language-aware symbol inventory.
- `build-map.json` — build/test/workflow/manifests topology.
- `impact.json` — current change impact against a selected Git base.
- `gaps.json` — capability/evidence gaps.
- `security-quality.json` — controls, risks and quality findings.
- `metrics.json` — measured indexing/graph statistics.
- `notes.md` — compact human augmentation brief.
- `dependabot-notes.md` — live dependency-security context when permissions allow.

## Non-negotiable rule

The index is evidence infrastructure. A discovered file/symbol is structural evidence, not proof that a feature is correct, secure, production-ready, competitive, or SOTA. Those claims require linked tests/evals/benchmarks/release evidence.
