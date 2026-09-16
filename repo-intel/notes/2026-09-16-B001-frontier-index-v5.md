# B001 — Frontier repository index v5

## Intent

Advance **B001 Repository intelligence spine** by promoting the repository index from a source/supply-chain graph into a build-facing frontier knowledge graph. This work also provides measured foundations for B002/B009 without claiming those batches complete.

## Concrete changes

- Added `scripts/repo_intel_deep.py` for deterministic direct dependency inventory, package scripts, workflow/build relationships, backend/Expo route discovery, environment-variable name references, bounded Git-history churn/freshness, graph centrality/hotspots, batch handoff evidence and compact lexical agent retrieval.
- Added `scripts/repo_intel_frontier.py` as the authoritative schema-v5 composition layer over the existing canonical `repo_index.py` semantic/supply-chain/architecture graph.
- Added `repo-intel/deep-index-contract.json` and expanded `repo-intel/config.json` / `repo-intel/query-contract.json` with the new outputs and precision/non-claim semantics.
- Added focused deep/frontier regressions.
- Promoted Make, dedicated Repository Intelligence CI and required Merge Readiness checks to the frontier CLI.
- Updated `AGENTS.md` so all AI models use the same frontier query interface that CI enforces.
- Fixed the required Merge Readiness snapshot base so `main` push events fall back to `origin/main` instead of receiving an empty pull-request base SHA.
- Updated the index benchmark to exercise the frontier path.

## Validation evidence

CI is the execution authority for this branch. The dedicated Repository Intelligence workflow compiles every repo-intelligence layer and runs `tests/test_repo_intel.py`, `tests/test_repo_intel_sota.py`, `tests/test_repo_intel_deep.py`, `tests/test_repo_intel_frontier.py`, and `tests/test_repo_index.py` before generating the graph. Merge Readiness independently runs the frontier contract, snapshot and augmentation-note gate inside its required quality/security job.

The implementation intentionally preserves deterministic/offline core indexing: semantic source analysis remains Git-blob cached; Git history is bounded to 600 commits and freshness is relative to the HEAD commit timestamp rather than wall-clock time.

## Security impact

- Environment **values are never indexed**. Only variable names, whether they appear in tracked `.env.example` files, and source-reference paths are emitted.
- Dependency inventory is offline direct-declaration evidence only. It does not pretend to know transitive resolution or vulnerability state; GitHub Dependency Graph / Dependabot remains authoritative for that evidence.
- Existing secret scanning, CodeQL, dependency review, malware, provenance and Gitleaks gates remain unchanged and authoritative.
- Workflow/build references are lexical evidence and preserve their precision label.
- Hotspot scores are explicitly triage signals, not security grades.

## Quality / performance impact

- Clean semantic content still reuses Git blob identities and the existing semantic cache.
- Added bounded Git-history scanning, route/env extraction and small structured-manifest parsing. `make repo-intel-bench` now measures the full frontier refresh so any latency regression is observable rather than hidden.
- Reverse-impact queries now include workflow/build edges and external dependency declarations where structurally connected.
- The compact `search-catalog.json` provides deterministic repo-native retrieval without requiring network embeddings for basic agent navigation.

## Dependency / Dependabot effect

No production or development dependency was added for the index. New index code is Python standard-library only. Existing Dependabot configuration and live-alert enrichment remain in place.

## Architecture / supply-chain / runtime-surface effect

The frontier layer composes with, rather than replaces, the canonical structured supply-chain/CODEOWNERS/architecture-boundary graph. It adds:

- Make target and workflow-to-file relationships;
- FastAPI-style and Expo file-route discoverability surfaces;
- environment-variable name/reference surfaces;
- deterministic history/centrality hotspot metadata;
- batch evidence state;
- agent search records;
- richer change-set and impact notes.

## Noticeable remaining gaps / next augmentation

- JS/TS symbols/imports remain conservative lexical evidence; validated compiler/SCIP ingestion is still the precision upgrade target.
- The dependency graph still needs validated CycloneDX/SPDX export and lockfile-level/transitive correlation rather than only direct/offline declarations.
- Graph diff currently uses current-head semantics plus Git path status; exact deleted-edge comparison requires persisted/base-ref semantic snapshots.
- Candidate-test selection does not yet rank tests using historical pass/fail/runtime evidence.
- Build nodes do not yet carry hermetic action fingerprints suitable for a real remote content-addressable build cache.
- Route discovery is structural; runtime reachability and authorization coverage need explicit integration evidence.
- Hotspot weighting should be calibrated against measured review defects/build regressions before it is used for prioritization policy.
- `evidence-noted` batch state deliberately does not infer completion; a future batch ledger needs signed/validated completion evidence.
