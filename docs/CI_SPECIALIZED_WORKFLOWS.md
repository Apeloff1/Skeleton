# CI tiers — build fast, qualify deep separately

The workflow directory contains hundreds of fine-grained assurance planes.
On every code update, running every deep game, native console, AI, storage,
product, ARM, packaging and governance matrix competes with source building.

## Daily fast PR lane

Merge Readiness is the **only** canonical protected-branch aggregate. It and
its required upstream jobs still execute automatically; no skipped, failed,
missing or cancelled job is treated as a pass. Backend Quality continues
lint/syntax and fail-closed security/policy scanners. Additional source and
security checks (secret scanning, malware, workflow input, dependency,
provenance, P0 boundary evidence) retain automatic scoped PR triggers.

## Specialized — manual, *not* waived

These workflows are tagged `[Specialized]` in GitHub Actions and run on
`workflow_dispatch` only. They no longer trigger on every PR/push:

- `ci.yml`
- `app-assembly.yml`
- `arm64.yml`
- `ai-product-completion.yml`
- `ai-p0-current-main-validation.yml`
- `p3t2-governed-storage.yml`
- `p3t2-governed-data.yml`
- `frontier-contracts.yml`
- `packaging-runtime-image.yml`
- `cost-admission-closure.yml`
- `governance-closure.yml`

In Backend Quality, the complete Jeeves/game suite and deep adversarial test
matrix also require manual `workflow_dispatch`. The security scanners,
Ruff/compile and policy audit steps remain on the ordinary path.

Use **Actions → select [Specialized] workflow → Run workflow → choose the
exact PR branch**. For an approvable release, execute the relevant full
qualifications at the *exact candidate commit* (including manual Backend
Quality and Merge Readiness), inspect all results and retain receipts.
GitHub `workflow_dispatch` normally runs on a selected ref; check the
actual head in every emitted report before release. The mere absence of a
specialist check means `unqualified`, not `passed`.

This change reclassifies redundant frequent **CI execution**, not quality
standards, professional story review, hardware validation, security
requirements or production P0 acceptance. The 20 game P0 plus CHAT/Dragon
and whole-app gates remain separate and non-compensable.

Machine-readable tier inventory: `machine/ci_workflow_tiers.json`.
Validator: `python scripts/check_ci_workflow_tiers.py`.
Tests: `python -m unittest tests.test_ci_workflow_tiers`.

### Workload comparison (workflow-level, not runtime-guaranteed)

The observed previous PR head scheduled 32 workflow runs for a single
update. Eleven individually heavy workflows from that eligible set are
now explicit manual specialists. Actual savings depend on the changed files,
GitHub matching rules and whether the operator launches specialists.
The five-job required Merge Readiness and remaining scoped safety checks
can still take time. No claim that every queued/failing historical Actions
run was cancelled or that the protected-branch aggregate is now optional.
