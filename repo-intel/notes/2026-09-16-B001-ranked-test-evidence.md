# B001 — ranked structural test evidence

## Intent

Advance B001 (Repository intelligence spine) by connecting source/change impact to ranked focused tests so agents and local validation can use machine time efficiently without weakening required integration, security, or release gates.

## Changed behavior / paths

- `scripts/repo_intel_test_evidence.py`
  - builds deterministic source-to-test evidence from direct test imports, explicit structural test links, bounded transitive imports, and existing reverse-impact candidates;
  - assigns explicit confidence/reason/precision/depth metadata;
  - aggregates ranked tests across an impacted file set.
- `repo-intel/test-evidence-contract.json`
  - defines structural-only confidence semantics and explicitly forbids interpreting ranking as coverage/sufficiency.
- `scripts/repo_intel_frontier.py`
  - writes `test-evidence.json`;
  - adds test-evidence metrics to the index/build map/doctor output;
  - enriches `impact.json` with `ranked_candidate_tests` and reason paths;
  - adds `query --kind tests` and per-file ranked tests;
  - keeps required full validation gates authoritative.
- `.github/workflows/repo-intelligence.yml`
  - compiles and tests the new layer and publishes test-evidence metrics.
- `repo-intel/config.json`, `repo-intel/query-contract.json`, `AGENTS.md`, and the merge-readiness contract now expose/require the layer.

## Validation evidence

Focused regressions in `tests/test_repo_intel_test_evidence.py` cover direct-vs-transitive ranking, explicit test relations, reason aggregation, and reverse-impact candidates. `tests/test_repo_intel_frontier.py` continues to cover the top-layer graph/cache invariants. The Repository Intelligence workflow executes both test files on the authoritative GitHub runner.

## Security impact

Neutral/positive. No test execution is skipped by policy; ranked evidence is an ordering hint only. The layer reads existing structural graph metadata and adds no secrets, network calls, or privileged operations.

## Quality / performance impact

Positive. High-confidence focused tests can be executed first for fast feedback while full integration/release matrices remain required. Ranking is deterministic and bounded to three transitive import levels to avoid graph explosion and false precision.

## Dependency / Dependabot impact

No new dependencies. Python 3.11 standard library only. Dependabot configuration unchanged.

## Architecture / supply-chain / runtime-surface effect

The repository knowledge graph now connects source/change impact to explicit validation evidence. This closes part of the code → impact → tests path while retaining evidence labels that distinguish AST, lexical, structural, and transitive inference.

## Remaining noticeable gaps / next augmentation

- Add historical test execution outcomes/durations so focused selection can optimize both relevance and cost without turning historical success into a correctness claim.
- Add artifact lineage from source/generated inputs to release outputs.
- Add stored base snapshots for deleted-edge semantic graph diffs.
- Add compiler/SCIP ingestion for higher JS/TS precision when available, retaining the current dependency-free fallback.
