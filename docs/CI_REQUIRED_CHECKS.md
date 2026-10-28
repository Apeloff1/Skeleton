# Required CI checks

The merge-critical pull-request gate is the single check **`Merge Readiness`**,
published by GitHub Actions (app id `15368`) from the `readiness` job of
`.github/workflows/merge-readiness.yml` (workflow name *Merge Readiness*).

The machine-readable source of truth is
[`.github/ci/required-checks.json`](../.github/ci/required-checks.json).
`scripts/check_required_checks_policy.py` runs in the `Quarantine Policy` lane
and fails closed whenever the workflow, this document,
`docs/MERGE_READINESS.md`, `scripts/configure_main_protection.sh`, or
`scripts/check_merge_readiness_contract.py` drift from that file, or when any
other workflow job publishes a check with the same required name.

## Required lanes

The summary job runs only after, and fails unless all of, these lanes succeed
for the same head SHA:

| Lane (check name) | Job id | Covers |
| --- | --- | --- |
| Quarantine Policy | `quarantine_policy` | merge-readiness contract, required-check policy, flaky-test quarantine registry |
| Unit | `unit` | canonical compile, and — when CI/CD change scope includes Python — `tests/run_unit.py` plus the complete `skeleton/testing` suite |
| Integration Smoke | `integration_smoke` | backend import against live MongoDB and the cross-subsystem integration matrix |
| Lint Type Security | `quality_security` | high-confidence security gates and full-history Gitleaks. Backend Ruff and frontend lint/typecheck stay with CI/CD when that lane runs them |
| PR Automation Tests | `pr_automation` | auto-merge and runner-v2 privileged contracts, repository machine contracts, filesystem/tool transaction boundaries |
| CI/CD | `ci` | reusable `.github/workflows/ci.yml` (restored in #4104): Frontend lint/typecheck/`test:*`/stability suites/`export:web`, Backend Lint, Backend Test, Backend Import Smoke, Skeleton GameForge, Java/Assembly accelerators, Jeeves School Reasoning, Cockpit Smoke, Docker Build (build-only). Per-lane checks appear as `CI/CD / <job>`; lanes whose inputs a PR does not touch are skipped (skip counts as success). |

A failed, cancelled, or skipped lane makes `Merge Readiness` fail. Repository
rules therefore need exactly one stable required-check name while the per-lane
checks keep detailed diagnostics.

## Fast versus slow checks

- **Fast merge path** — the lanes above. They run on every non-draft pull
  request to `main` and on every `main` push.
- **Defence in depth** — dedicated workflows such as Backend Quality, Secret
  scanning, CodeQL, Malware Gate, and Artifact Policy keep running and are
  visible on the PR, but are not part of the required summary unless the policy
  file promotes them.
- **Slow / scheduled / release** — load, provenance, archive, and night-shift
  workflows triggered by `schedule`, `workflow_run`, `workflow_dispatch`, or
  release tags stay outside the fast merge summary.

## Concurrency

Pull-request runs use per-PR concurrency and cancel an older in-progress run
when a newer commit supersedes it. `main` push runs are grouped per SHA and are
never cancelled, so rapid merges cannot erase the canonical result for a head.

## Flaky tests

Flaky-test exceptions are recorded in `.github/ci/flaky-quarantine.json` and
validated by `scripts/check_flaky_quarantine.py`. Every entry must name the
exact test/check, link an issue, name an `@owner`, explain the reason, and
expire within 30 days. Security evidence requirements, dependency auditing, and
broader temporary-exception policy remain defined in `docs/SECURITY_CI_POLICY.md`.

## Checking a PR or commit

`scripts/merge_readiness_status.py` is a read-only reporter that uses your
local `gh` authentication:

```bash
python scripts/merge_readiness_status.py --pr 1234        # a pull request head
python scripts/merge_readiness_status.py --ref main       # current main head
python scripts/merge_readiness_status.py --sha <sha> --json
```

It prints one deterministic verdict (`READY`, `NOT_READY`, or `PENDING`) with
every required lane, PR mergeability, and whether `main` protection actually
enforces the policy. Exit codes: `0` ready, `1` not ready, `3` pending,
`2` usage or API error.

## Repository rule

Repository branch protection or a ruleset for `main` must require
**`Merge Readiness`** (app id `15368`) before merge. Workflow source defines and
aggregates the check, but repository administration must enforce it. The
owner-side command is:

```bash
scripts/configure_main_protection.sh --dry-run   # show the payload
scripts/configure_main_protection.sh --apply     # admin-only: apply and verify
scripts/configure_main_protection.sh --verify    # admin-only: verify
```

Do not replace the deterministic summary with a changing list of individual job
names. Renaming the workflow, job, or a lane is a policy change: update
`.github/ci/required-checks.json` and the protection configuration together.


## Operational enforcement gap — 2026-10-28

At main `6cdd2bb5e7b5f186671790b1ea63cf1dded8c020`, live GitHub branch metadata reported `protected=false` and no enforced required checks. A successful workflow or committed required-check policy is **not** equivalent to branch protection. The owner-side `scripts/configure_main_protection.sh --apply` and `--verify` commands require an administrative GitHub CLI credential and must both complete before release certification. The automatic reconciliation lane rejects merge mutations if `main` is unprotected or protection cannot be read. Manual/direct pushes are not protected until GitHub branch protection is enabled. Review `docs/security/SECURITY_STATUS.md` for the current operational and production qualification blockers.

## Tagged release publication guard

`scripts/release_governance_verdict.py --repo Apeloff1/Skeleton --sha <exact-40-character-main-sha> --branch main` is a read-only, fail-closed publication preflight, exercised by the tag image publication and reproducible-release jobs. It verifies current branch head identity, GitHub branch protection with the expected Merge Readiness app binding, and successful exact-head **main push** runs for `Merge Readiness`, `Malware Gate` and `Secret scanning`. Triggered path-scoped main checks (Workflow Input Security, Backend Quality, Repository Hygiene Gate and App Foundation E2E) are negative evidence if failing or incomplete, but an absent path-scoped check is not falsely counted as a pass. PR-only Dependency Review and Artifact Policy must be handled via their matching PR evidence. The source gate cannot certify external KMS, writer-custody or disaster-recovery qualification.
