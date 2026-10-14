# Jeeves and AI capability intelligence — October 13, 2026

**Milestone branch:** `feat/jeeves-ai-capability-intelligence-20261013`\
**Depends on:** draft Jeeves appwide fabric PR #3718; not independently mergeable to main.\
**Canonical owner:** `skeleton/ai/game_builder/` existing governed Jeeves/Studio appwide adapter.\
**Trust boundary:** deterministic code inspection only; no AI model, tool authority, shell, source mutation, or promotion.

## Implemented, source-linked deliverables

| Milestone | Runtime action | Deterministic output | Hard limitation |
| --- | --- | --- | --- |
| JAI-01 static interface discovery | `ai.contracts` | Python AST top-level public declarations/classes/method names, import syntax; source SHA and parse status; explicit heuristic exports for TS/JS/Rust/Go/Java/GDScript/C#/Kotlin/Swift | Syntax declarations are NOT verified callable contracts; no module loading or execution |
| JAI-02 change impact preflight | `ai.impact` | Dependency edges and direct dependents within an exact selected source set; source SHA, graph receipt | Graph is incomplete by construction; no claim of safe refactoring or entire-repo impact |
| JAI-03 minimal working context | `ai.context` | Query-ranked public symbol names, static import names, paths, source digests; bounded metadata size | Character budget is NOT model token count; no source text, private credentials or cross-file full memory |
| JAI-04 exact and near duplicate scouts | `ai.duplicates` | SHA-256 equal-content groups and bounded normalized Python-token shingle near matches, with similarity values | Near matches are review candidates; no removal or module conflation |
| JAI-05 operational registration | existing `JeevesAppwideRuntime.invoke` | Four registered read-only IDs, common input/output/inventory receipt and same Studio token/origin boundary | No new generic callable tool or source writer |
| JAI-06 regression verification | `tests/test_game_builder_jeeves_capability_intelligence.py` and existing appwide suite | malicious paths, restricted files, symlink swaps, exact stale SHA, deterministic context, syntax failure, graph edges, duplicate classification, bounded budgets, no mutation | Added tests are not equivalent to passing CI until exact-head jobs succeed |

The implementation is an **on-demand batch inspector** (up to 48 explicitly selected repository paths at a time, each up to 128,000 UTF-8 bytes) within the established inventory. This avoids loading ~58,884 scanned sources or entire files into a model context. A caller should page inventory search and study selected groups, carrying `inventory_snapshot` plus per-source `source_sha256` across decisions. Re-scan when working tree changes; optional expected source digests reject same-length changes. A repository-level continuous watcher and full indexed search database are **not** in this batch.

The Python AST analyzer does not import source modules, evaluate decorators or annotations, call `exec`/`eval`, or fetch URLs. Other language parsers are **heuristic and explicitly labelled**; regex evidence is not schema verification. A parse failure reports `parse_failed` rather than inventing exports. Only the existing `AppwideInventory._safe_file` reviewed reader can access source; private/credential paths and symlinks fail closed. File contents are not present in context packets or duplicate result receipts.

## L00–L13 implementation acceptance map

| Level | Acceptance / what is still needed |
| --- | --- |
| L00 Intent & ownership | Additive static intelligence; governed Jeeves appwide owner; no new model authority |
| L01 Architecture & dependencies | Depends on existing `AppwideInventory` and `JeevesAppwideRuntime`; all other app services remain canonical |
| L02 Inputs & data contracts | Exact bounded path list, optional inventory/source hashes, objective, fixed budgets and threshold |
| L03 Outputs & receipts | Source SHA, snapshot, deterministic action digest, incomplete-coverage flags, explicit read-only status |
| L04 Security & privacy | No raw code packets, private-path reads, symlink follow, generic import/run, or implicit authorization |
| L05 Runtime control flow | Studio/Jeeves invoke → registered adapter → bounded source read → pure AST/regex/dedup/graph → digest |
| L06 Persistence | None; results are ephemeral, reproducible projections and not durable authority |
| L07 Failure & recovery | Stale snapshot, source SHA mismatch, inaccessible path, parse failure and limits fail closed or report explicitly |
| L08 Observability | Inspected versus unexamined file counts, parse status, graph incompleteness, source receipts |
| L09 Economics & budgets | 48 source paths, 128 KB each, 10k tokens for fingerprint input, 20k *characters* context maximum |
| L10 Evaluation | Focused adversarial Python tests and preexisting appwide suite added to exact-head workflow |
| L11 Deployment & compatibility | No extra service/dependency; full Windows/Linux workflow and architecture gates remain to be verified |
| L12 Operator controls | No operational effects; edit/deploy/weight-promotion still require separate governed controls |
| L13 Rollback & release | Revert additive module, registry rows, tests and workflow; preserve existing appwide inventory and tool IDs |

## Validation commands

```bash
python -m py_compile skeleton/ai/game_builder/jeeves_capability_intelligence.py
python -m unittest tests.test_game_builder_jeeves_capability_intelligence tests.test_game_builder_jeeves_appwide_fabric -v
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
python scripts/check_provider_bootstrap.py
python scripts/check_enterprise_ai_superiority.py --json
python scripts/check_enterprise_ai_implementation_notes.py --json
```

The PR's exact-head Windows and Ubuntu jobs should run both static intelligence and the full inherited Jeeves story-canon targeted suites. A skipped, canceled, failing or absent gate does not certify completion.

## Next substantive Jeeves + AI milestones (not declared complete)

1. **JAI-07:** Extract route/auth/effect contracts by language-specific parsers and reconcile UI controls to backend executor IDs. An export becomes *bound* only after real invocation and policy regression.
2. **JAI-08:** Incremental, crash-safe and privacy-scoped persistent symbol/dependency index with exact content-hash invalidation, atomic snapshots, deterministic paging, and stale-source revocation.
3. **JAI-09:** Real application-graph blast-radius review across backend, frontend, packages, platform/engine adapters and test evidence, using independently checked route/contract edges.
4. **JAI-10:** Jeeves-assisted draft patches through existing approved source-proposal workflow; sandbox/mirror, security tests, benchmarks and rollback evidence **before** operator merge.
5. **JAI-11:** Separate holdout-based shadow-weights promotion from normal weights and hyperweights, measured by reproducible independent evaluation; no weight modification without evidence.
6. **JAI-12:** Model-grounded chapter/editor/forge actions using the supervised director, carrying witnessed/player-visible narrative and current continuity receipts only; no spoiler or private-context crossovers.
7. **JAI-13:** Real installed model inference, game production builds and platform-specific acceptance with exact-head source identity, costs, backpressure and recovery.

**Claims:** This batch advances static knowledge of selected source contracts and supports much cheaper, better-grounded future Jeeves actions. It does *not* make every file operable, complete all AI models, finish studio integration, or certify a release. No measured percentage of full product capability completion is claimed without a current functional acceptance census.
