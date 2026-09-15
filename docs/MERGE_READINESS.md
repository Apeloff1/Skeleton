# Merge readiness and required-check policy

A pull request is merge-ready only when the repository can explain *why* it is
safe to merge from the PR UI and committed evidence. A green button produced
by rerunning failures until one passes is not evidence.

## Readiness contract

Before merge, all of the following must be true:

1. The PR targets the intended base and has no unresolved merge conflict.
2. Every check configured as required for the protected base branch is green
   for the current head commit, not for an older commit.
3. Repository security gates relevant to the change are green, including
   secret scanning and workflow-security checks.
4. Repository artifact-policy checks, when applicable to tracked-content
   changes, are green.
5. Backend/frontend lint, type, test, dependency, and build checks applicable
   to the touched surfaces are green.
6. Review conversations that identify correctness or security defects are
   resolved by code/test changes or an explicit tracked follow-up accepted by
   the maintainer.
7. The PR description states important dependencies, rollout/rollback concerns,
   and which backlog issues it closes or advances.
8. No check is being ignored merely because the failure is intermittent.

If the current head SHA changes, previous green status is historical evidence,
not merge authorization; required checks must evaluate the new head.

## Required checks

Repository rules/branch protection are the enforcement source of truth. The
protected `main` branch should require the canonical CI/security checks exposed
by workflows under `.github/workflows/`, including the repository's core
CI/quality jobs and dedicated security/policy jobs that apply to the change.

The repository-level deterministic merge gate is implemented by
`.github/workflows/merge-readiness.yml`. Its final job name is **Merge Readiness**
and it fails unless all of these constituent gates succeed for the same head:

- **Quarantine Policy** — validates the machine-readable flaky-test registry;
- **Unit** — compiles the canonical package and runs `tests/run_unit.py`;
- **Integration Smoke** — installs the backend runtime and imports the live app
  against the workflow MongoDB service;
- **Lint Type Security** — runs backend Ruff, the canonical frontend lint/type
  and high-confidence security gates, plus the pinned full-history Gitleaks scan.

`main` branch protection should require the stable **Merge Readiness** job. The
existing dedicated workflows remain valuable defense in depth and may also be
required, but the aggregate job is the one deterministic repository summary for
merge authorization. Superseded pull-request runs are cancelled by workflow
concurrency so a stale head cannot consume capacity or be mistaken for current
evidence.

Workflow/job names should remain stable once configured as required. Renaming a
required job is a policy change: update branch/ruleset configuration in the
same maintenance window and verify a fresh pull request is blocked while the
check is pending or failing.

The GitHub App used by automation may not have administration permission to
read or modify branch protection. In that case, do not infer settings from
repository contents. A maintainer with repository administration access must
verify that the documented required set is actually enforced after workflow
changes.

## Flaky-test policy

A flaky failure is a defect, not a pass. When a check fails intermittently:

- Preserve the first failing logs/artifacts and record the failing seed, shard,
  platform, or test name when available.
- Reproduce locally or in a focused CI job before broad reruns.
- Open/link a GitHub issue containing owner, impact, reproduction evidence, and
  a removal target.
- Prefer fixing the race, clock dependency, external-network dependency, shared
  state, or nondeterminism immediately.

A test may be quarantined only when keeping it in the blocking path would stop
unrelated work and the quarantine is explicit. A quarantine change must:

- name the exact tests/checks affected;
- link a tracking issue;
- name an owner;
- include an expiry/review date or concrete removal condition;
- preserve a non-blocking execution path so failures stay visible; and
- avoid reducing coverage of security-critical behavior without an equivalent
  deterministic gate.

The canonical registry is `.github/ci/flaky-quarantine.json`. Every entry is
validated by `scripts/check_flaky_quarantine.py` on every Merge Readiness run.
Entries must include an exact test/check identifier, linked issue, explicit
`@owner`, explanation, and ISO expiry date. Expired entries fail the gate and a
new quarantine cannot be created more than 30 days ahead, preventing silent or
indefinite exclusions. `non_blocking_check` may name the check that continues to
execute the quarantined test visibly.

Repeatedly pressing **Re-run jobs** until a failure disappears is never a valid
quarantine mechanism.

## Security-sensitive changes

For authentication/authorization, secret handling, subprocess execution,
deserialization, proxy trust, request framing/body limits, rate limiting,
workflow permissions/actions, or artifact provenance:

- require adversarial regression coverage for the defect or boundary;
- keep fail-closed behavior explicit in tests;
- avoid bundling unrelated refactors that make the security delta hard to
  review; and
- preserve a rollback path whenever behavior reaches production.

A superseding/consolidation PR must identify the older PRs it replaces. Do not
merge overlapping implementations simply because each branch is green in
isolation.

## How a contributor decides whether to merge

Use the pull request's **latest head commit** and Checks/Files changed views.
The decision should be mechanical:

- required check pending -> wait;
- required check red -> fix or explicitly quarantine under this policy;
- head changed after green run -> wait for the new run;
- unresolved correctness/security review -> resolve it;
- branch protection/ruleset status unknown -> verify it with an administrator;
- all required evidence green/current and reviews resolved -> merge is allowed.

After an emergency or manual merge, restore normal branch/ruleset enforcement
before routine work resumes and open an issue for any bypassed evidence.
