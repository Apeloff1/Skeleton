# Required CI checks

The merge-critical pull-request gate is the single check **`CI/CD / Merge Readiness`**.

That summary job runs only after, and fails unless all of, these required lanes succeed:

- Backend Lint — backend lint, syntax, toolchain contract, and process-safety check.
- Security Gate — process, deserialization, SAST, JavaScript process-alias, workflow-security, repository secret-hygiene scanners, and the flaky-quarantine registry validator.
- Skeleton GameForge — core unit/regression suite and representative CLI/runtime smoke commands.
- Jeeves School Reasoning — focused reasoning regression suite.
- Cockpit Smoke — cockpit integration smoke path.
- Backend Test — backend test suite against MongoDB with coverage collection.
- Backend Import Smoke — clean dependency install plus application import/startup smoke.
- Frontend — frozen dependency install, lint, typecheck, and production export.

A failed, cancelled, or skipped required lane makes `Merge Readiness` fail. This gives repository rules one stable required-check name while preserving detailed per-lane diagnostics.

Pull-request runs use per-PR concurrency and cancel an older in-progress run when a newer commit supersedes it. Push validation is not cancelled so rapid pushes cannot continuously starve branch validation.

Flaky-test exceptions are recorded in `.github/ci/flaky-quarantine.json` and validated by `scripts/check_flaky_quarantine.py`. Every entry must name the exact test/check, link an issue, name an `@owner`, explain the reason, and expire within 30 days. Security evidence requirements, dependency auditing, and broader temporary-exception policy remain defined in `docs/SECURITY_CI_POLICY.md`.

Slow release/load/provenance workflows remain outside the fast merge summary unless their owning policy explicitly promotes them.

## Repository rule

Repository branch protection or a ruleset for `main` must require **`CI/CD / Merge Readiness`** before merge. Workflow source can define and aggregate the check, but repository administration must enforce it; do not replace the deterministic summary with a changing list of individual job names.
