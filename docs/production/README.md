# Production — Skeleton FULL APP COMPLETION / ROLLOUT

Owner lane: **Production** (schedules, dependency board, risk burn-down).
Enforcement of required checks on `main`: **Grenn** (DevOps).
Status and blockers report to **Grok Bot** (as Battle Brothers).

## Documents

| Doc | Purpose |
| --- | --- |
| [DEPENDENCY_BOARD.md](DEPENDENCY_BOARD.md) | Live open-PR waves and critical path |
| [RISK_REGISTER.md](RISK_REGISTER.md) | Schedule / quality risks with burn-down triggers |
| [MERGE_READINESS_POLICY.md](MERGE_READINESS_POLICY.md) | Operational pointer to the closed #127 policy + Grenn follow-ups |

Canonical merge gate (already on `main`):

- Workflow: `.github/workflows/merge-readiness.yml`
- Required check name: **Merge Readiness**
- Machine-readable source of truth: [`.github/ci/required-checks.json`](../../.github/ci/required-checks.json)
- Human policy: [docs/CI_REQUIRED_CHECKS.md](../CI_REQUIRED_CHECKS.md), [docs/MERGE_READINESS.md](../MERGE_READINESS.md)

## Refresh

1. List open PRs: `gh pr list --repo Apeloff1/Skeleton --state open --limit 50`
2. For each PR, note draft?, base branch (stack if base ≠ `main`), and Merge Readiness / lane status via Checks or `python scripts/merge_readiness_status.py --pr <n>`
3. Update DEPENDENCY_BOARD.md waves and RISK_REGISTER.md severities
4. Do **not** claim competitor parity or rollout-ready unless **Merge Readiness** is green on the exact head **and** `main` protection actually requires it (`scripts/configure_main_protection.sh --verify`)

## AAA scope honesty

Feature volume is high. Merge order favors reliability and stacked bases over new surface area. Drafts and PRs that disclaim hardware-verified / legal / release authority stay out of the critical path until those gates are real.
