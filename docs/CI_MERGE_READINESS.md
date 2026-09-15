# CI merge-readiness policy

`CI/CD / Merge Readiness` is the deterministic pull-request gate for the repository. A change is merge-ready only when that job succeeds.

## Required fast checks

The summary consumes these jobs from `.github/workflows/ci.yml`:

| Required lane | Contract |
| --- | --- |
| Backend Lint | Repository toolchain contract, pinned Ruff correctness lint, Python compilation, process-invocation safety gate |
| Skeleton GameForge | Core unit/regression suite plus representative CLI/runtime smoke commands |
| Jeeves School Reasoning | Focused reasoning-stack unit suite |
| Cockpit Smoke | Cockpit integration smoke path |
| Backend Test | Backend tests against MongoDB with coverage collection |
| Backend Import Smoke | Fresh dependency install and application import/startup smoke |
| Frontend | Frozen install, lint, typecheck, and production web export |
| Security Fast | High-confidence tracked-file secret scan, process-execution static guard, and flaky-quarantine policy validation |

Any failed, cancelled, or skipped required lane makes `Merge Readiness` fail. The summary therefore provides one stable branch-protection/check-rule target instead of requiring maintainers to track the individual job list manually.

Dependency/SBOM auditing remains in `dependency-security.yml`; it is triggered when dependency manifests or dependency-security policy change. Slow release, provenance, load/soak, and specialized subsystem workflows remain separate from the fast pull-request merge gate unless their owning policy promotes them to this required set.

## Concurrency

Pull-request CI uses one concurrency group per PR and cancels superseded runs. Push validation is not cancelled in progress so an active `main` validation cannot be starved by rapid successive pushes.

## Flaky tests

Required checks must not use `continue-on-error`, unconditional `|| true`, or silent test exclusion to hide a flaky test. A temporarily quarantined test must be recorded in `.ci/flaky-tests.json` with:

- a unique `id`;
- the exact test identifier/path;
- an accountable `owner`;
- a concrete `reason`; and
- an ISO `expires` date no more than 30 days in the future.

`scripts/check_flaky_quarantine.py` is part of the required security/policy lane. Expired, malformed, duplicate, or open-ended entries fail CI. Renewing a quarantine requires an explicit reviewed commit; the preferred resolution is to fix the test and remove the entry.

## Secrets and security

`scripts/check_secrets.py` scans tracked UTF-8 text for conservative, high-confidence credential signatures on every pull request. Positive findings fail closed; credentials must be removed and rotated rather than allowlisted. `backend/scripts/check_process_safety.py` remains the static guard against unsafe host-process invocation patterns.

## Branch protection / rulesets

Configure repository rules to require the exact check name `CI/CD / Merge Readiness` for changes targeting `main`. The workflow is intentionally designed so this one check summarizes all fast merge-critical lanes. Repository-administration policy is separate from workflow source and should point only at this stable summary check.
