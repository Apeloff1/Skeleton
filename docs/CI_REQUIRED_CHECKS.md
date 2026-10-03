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
| Unit | `unit` | canonical unit runner and the complete canonical domain suite |
| Integration Smoke | `integration_smoke` | backend import against live MongoDB and the cross-subsystem integration matrix |
| Lint Type Security | `quality_security` | backend Ruff, canonical lint/type/high-confidence security gates, full-history Gitleaks secret scan |
| PR Automation Tests | `pr_automation` | auto-merge and runner-v2 privileged contracts, repository machine contracts, filesystem/tool transaction boundaries |

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
