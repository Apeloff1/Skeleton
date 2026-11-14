# Merge Readiness: source qualification consolidation — 14 November 2026

Status: **review-only, exact-head CI required, no first-install or release signoff**.

## Problem and preserved authority
The repository's CI-tier validator enforces at most 20 independently subscribed, non-operational workflows. The reviewed candidate had 45, partly because numerous source-only PR paths subscribed separately after the canonical Merge Readiness workflow already performed broader integration, security and native-Source verification. Raising the cap, dropping regressions, marking them continue-on-error or accepting skipped checks would conceal problems instead of fixing the workflow control plane.

## Implementation
Twenty-five existing source workflows remain at their original paths, retain their own fail-closed jobs, explicit dependency installs, immutable PR-head checkouts, and read-only GITHUB_TOKEN permissions. Their `pull_request` event subscriptions are replaced by `workflow_call`; pre-existing unprivileged manual `workflow_dispatch` is retained where supported. A single protected Merge Readiness run on the PR head invokes each same-repository workflow by relative file path; no cross-repository or floating-ref imports are introduced.

Each call is its own named `source_NN` job. `source_qualification_gate` explicitly needs all 25, checks the complete structured `needs` result set for `success`, and rejects missing, skipped, cancelled or failed source lanes. The existing required `ci` lane depends on that gate and on PR accepts only its `success` status, while main's independently qualified `push` and `workflow_dispatch` runs retain their CI/CD execution without treating PR-only source suites as a main qualification claim.

The six published Merge Readiness aggregate inputs remain `quarantine_policy`, `unit`, `integration_smoke`, `quality_security`, `pr_automation`, and `ci`; required check names and the separate privileged `pull_request_target` hold are not modified. Workflow-call conversion does change the visible nested check presentation and is therefore not itself evidence that any external branch protection will accept the head; query the live ruleset before any merge.

## Registered source calls
01. `source_01` — `.github/workflows/backend-literal-lazy-loader-qualification.yml`
02. `source_02` — `.github/workflows/ci-surface-hold-source-qualification.yml`
03. `source_03` — `.github/workflows/discourse-job-identity-qualification.yml`
04. `source_04` — `.github/workflows/draft19-gguf-source-qualification.yml`
05. `source_05` — `.github/workflows/ecosystem-api-import-qualification.yml`
06. `source_06` — `.github/workflows/expo-export-content-evidence-qualification.yml`
07. `source_07` — `.github/workflows/first-install-source-qualification.yml`
08. `source_08` — `.github/workflows/frontier-cpu-determinism-qualification.yml`
09. `source_09` — `.github/workflows/galaxy-forge-roundtrip-qualification.yml`
10. `source_10` — `.github/workflows/gameforge-conductor-b039-qualification.yml`
11. `source_11` — `.github/workflows/gameforge-eight-native-scene-qualification.yml`
12. `source_12` — `.github/workflows/gameforge-source-archive-qualification.yml`
13. `source_13` — `.github/workflows/harbor-patrol-cli-qualification.yml`
14. `source_14` — `.github/workflows/harbor-studio-source-qualification.yml`
15. `source_15` — `.github/workflows/jeeves-bounded-canonical-evidence.yml`
16. `source_16` — `.github/workflows/jeeves-game-builder-quality-qualification.yml`
17. `source_17` — `.github/workflows/jeeves-integrated-source-qualification.yml`
18. `source_18` — `.github/workflows/jeeves-laptop-dispatcher-source-tests.yml`
19. `source_19` — `.github/workflows/jeeves-native-sqlite-source-qualification.yml`
20. `source_20` — `.github/workflows/mainline-failure-regression-qualification.yml`
21. `source_21` — `.github/workflows/masterplan-421-dossier-integrity.yml`
22. `source_22` — `.github/workflows/native-batch-operator-admission-qualification.yml`
23. `source_23` — `.github/workflows/native-qualification-report-custody.yml`
24. `source_24` — `.github/workflows/operational-literal-dispatch-qualification.yml`
25. `source_25` — `.github/workflows/perf-profiler-literal-target-qualification.yml`

## Fail-closed checks and independent holds
- The literal source registry at `machine/ci_workflow_tiers.json` and the separate 25-lane constant in `scripts/check_ci_workflow_tiers.py` must agree in membership and order.
- The tier checker rejects renewed standalone PR/push/schedule triggers on these source workflows, missing reusable calls, untrusted token privileges, missing rollup inputs, and lost CI/CD dependency.
- `tests/test_ci_workflow_tiers.py` mutates child subscriptions, caller bindings and fail-closed CI/CD result equality; each mutation must be denied.
- Source-only suites are not proof of installed Windows 11/WSL2, native live GGUF inference, hardware pressure/recovery, real Godot export, final release provenance, or external device qualification.
- Required CodeQL/security/malware/dependency/hygiene gates continue independently. `PR Merge Hold Gate` and review-only no-merge/no-auto-merge/no-release instructions remain effective until final-head trusted evidence is complete.
