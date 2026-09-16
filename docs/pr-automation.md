# PR automation index

`Skeleton` PR automation is a fail-closed control plane for evaluating pull
requests, publishing a trusted merge-readiness status, and optionally merging a
single already-approved head SHA. Its primary design rule is that automation
must lose authority when state is ambiguous.

## Architecture

The system has four layers:

1. **Snapshot**: GitHub PR, CI, review, thread, scope, and branch state are
   collected into an immutable `PRSnapshot`.
2. **Policy**: the pure evaluator returns `IGNORE`, `HOLD`, `READY`, or `MERGE`
   plus a deterministic policy/snapshot fingerprint.
3. **Index**: every material state transition and mutation result is written to
   the SQLite event index and exported as JSONL.
4. **Apply**: mutation is separately authorized, fully revalidated, checked
   against a protected base branch, claimed idempotently, and sent to GitHub
   with the expected head SHA.

The privileged workflow uses `pull_request_target`, but always checks out the
repository default branch. It never checks out, imports, or executes code from
the pull-request head. The same trusted workflow publishes the
`PR Automation Gate` commit status.

## Server-side authority

Client-side revalidation is not enough by itself: an approval, status, or base
branch can change in the final milliseconds before a merge request. Apply mode
therefore refuses to mutate unless GitHub reports the target branch as
**protected**. The repository ruleset is the final server-side authority in
that race window.

The supplied ruleset bootstrap requires:

- pull requests for `main`;
- stale approvals dismissed on push;
- approval from someone other than the last pusher;
- review threads resolved;
- deletion and non-fast-forward updates blocked;
- the trusted `PR Automation Gate` status;
- strict/up-to-date status checks.

Plan the ruleset without changing GitHub:

```bash
python -m skeleton.pr_automation.ruleset --repo Apeloff1/Skeleton
```

After reviewing the JSON, an owner can apply it with an admin-capable token:

```bash
GH_TOKEN=... python -m skeleton.pr_automation.ruleset \
  --repo Apeloff1/Skeleton --apply
```

The normal Actions token intentionally cannot administer repository rulesets.
The bootstrap is dry-run by default and updates an existing ruleset with the
same name instead of silently creating duplicates.

## CI gate

The repository already has an always-on `Merge Readiness` workflow whose final
`Merge Readiness` job aggregates the canonical quarantine, unit, integration,
and lint/type/security gates. PR automation uses that exact check name by
default. This avoids requiring path-filtered workflows directly, which can
otherwise deadlock documentation-only PRs because a required check is never
created.

`PR_AUTOMATION_REQUIRED_CHECKS` may override the default with an exact
comma-separated set. Apply+merge refuses to start if required checks are
disabled or the set is empty. The automation's own `PR Automation Gate` status
is explicitly excluded from CI aggregation so the gate cannot depend on itself.

Completed `neutral` or `skipped` checks are not treated as success for a
required gate. Re-runs are deduplicated by check/provider recency, while
same-named results from different providers are combined pessimistically so a
passing third-party check cannot overwrite another provider's failure.

## Review safety

By default, readiness requires one current approval, no active
`CHANGES_REQUESTED` review, and zero unresolved review threads.

An approval only counts toward the automated threshold when its `commit_id`
matches the current PR head SHA. A push therefore invalidates approval for the
automation immediately even before a server-side stale-review rule is taken
into account. Dismissed or superseded reviews stop counting because only each
reviewer's latest non-comment review state is used.

## Apply sequence

A merge attempt follows this order:

1. collect the initial snapshot;
2. evaluate and index it;
3. publish `PR Automation Gate` for that head;
4. fetch the complete snapshot again;
5. re-run policy and require the same deterministic action plan;
6. require the base branch to report `protected=true`;
7. atomically claim the action idempotency key;
8. call GitHub's merge API with the expected head SHA;
9. index success or failure.

If any policy-relevant snapshot field changes between steps 1 and 4, the plan
is discarded. This covers changes to the head or base SHA, CI, approvals,
change requests, review threads, mergeability, diff metrics, fork state, and
other indexed snapshot data.

`PR_AUTOMATION_MAX_MUTATIONS` is a **run-wide** budget. The workflow fixes it to
`1`; scanning 25 PRs cannot merge 25 PRs. Once the budget is consumed, later
PRs are still evaluated and indexed but cannot mutate during that run.

## Fail-closed edge cases

The engine holds instead of merging when it encounters any of the following:

- draft, closed, merged, conflicting, blocked, behind, unstable, hook-managed,
  unknown, or newly introduced merge-state values;
- a missing/deleted head repository or a fork when fork merging is disabled;
- missing, pending, failed, skipped, neutral, unknown, or incompletely
  paginated required CI;
- renamed required checks;
- incomplete review history;
- approvals attached to an older head SHA;
- active requested changes;
- unknown or unresolved review-thread state;
- unsupported base branches;
- negative/invalid change metrics or configured scope ceilings;
- base protection being removed;
- policy-relevant state changing during apply;
- duplicate webhook/schedule delivery;
- a mutation that was already successfully claimed;
- an in-flight action claim that has not yet expired;
- corrupted event hash chains;
- malformed integer/boolean configuration;
- GitHub rate limiting, API failure, GraphQL failure, or pagination uncertainty;
- exhausted run-wide mutation budget.

Transient HTTP 429/5xx/network failures and 403 secondary-rate-limit responses
with `Retry-After` are retried with bounded backoff. Persistent failures remain
fail-closed.

## Event index

`.pr-automation/index.sqlite3` uses WAL mode, full synchronous writes, busy
timeouts, one-writer workflow concurrency, and per-PR SHA-256 event chaining.
It stores:

- append-only evaluation/action events;
- snapshot and policy fingerprints;
- current-state projection;
- idempotency claims and attempt counts;
- retryable failed actions and stale in-flight recovery.

`.pr-automation/index.jsonl` is uploaded as a human-readable workflow artifact.
Repeated observation of an identical state is deduplicated, while a policy
change creates a new auditable event even when the PR itself is unchanged.

### Durability boundary

Actions cache is recovery storage, not an immutable compliance archive: caches
can eventually be evicted and the workflow artifact has finite retention. The
hash chain detects tampering or inconsistency **within the retained index**; it
does not prove that an evicted historical database never existed. For long-term
compliance, ship the JSONL artifact to durable object storage or another
append-only audit system.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `PR_AUTOMATION_MODE` | `observe` | `observe` or `apply` for non-manual runs |
| `PR_AUTOMATION_ALLOWED_BASES` | `main` | Comma-separated eligible base branches |
| `PR_AUTOMATION_REQUIRED_CHECKS` | `Merge Readiness` | Exact required check names |
| `PR_AUTOMATION_REQUIRED_APPROVALS` | `1` | Current-head approvals required |
| `PR_AUTOMATION_REQUIRE_CHECKS` | `true` | Require known passing CI |
| `PR_AUTOMATION_REQUIRE_NO_CHANGES_REQUESTED` | `true` | Block active requested changes |
| `PR_AUTOMATION_REQUIRE_RESOLVED_THREADS` | `true` | Require all visible threads resolved |
| `PR_AUTOMATION_ALLOW_FORK_MERGE` | `false` | Permit fork mutation after all other gates |
| `PR_AUTOMATION_MERGE_WHEN_READY` | `false` | Create/execute merge actions when ready |
| `PR_AUTOMATION_MERGE_METHOD` | `squash` | `merge`, `squash`, or `rebase` |
| `PR_AUTOMATION_MAX_CHANGED_FILES` | `250` | PR scope ceiling |
| `PR_AUTOMATION_MAX_LINE_DELTA` | `20000` | Additions + deletions ceiling |

The workflow fixes `PR_AUTOMATION_MAX_MUTATIONS=1`. Invalid ranges are rejected
rather than silently clamped.

## Deployment sequence

A safe rollout is intentionally staged:

1. merge the automation with `PR_AUTOMATION_MODE=observe` and
   `PR_AUTOMATION_MERGE_WHEN_READY=false`;
2. confirm `PR Automation Gate` updates correctly on PR, review, CI-completion,
   scheduled, and manual events;
3. dry-run and then install the repository ruleset;
4. confirm `main` reports protected;
5. keep `Merge Readiness` (or another reviewed stable aggregate) in
   `PR_AUTOMATION_REQUIRED_CHECKS`;
6. only then set `PR_AUTOMATION_MERGE_WHEN_READY=true` and switch mode to
   `apply` if automatic merging is desired.

A manual dispatch can target one PR and override mode for a single run.
Scheduled runs scan the 25 most recently updated open PRs and repair missed
webhook/status transitions.

## Typical uses

**Audit-only fleet view.** Keep observe mode on permanently. The index becomes a
queryable history of why each PR was ready or held without performing mutations.

**Conservative auto-merge.** Protect `main`, require `Merge Readiness`, current
approval, no change requests, and resolved threads; then enable apply and
merge-when-ready. At most one PR is merged per workflow run.

**Dependency/security PRs.** Override the required-check set if a dedicated
aggregate security gate is always present for that PR class. Missing checks hold
rather than being interpreted as not applicable.

**Fork intake.** Leave `PR_AUTOMATION_ALLOW_FORK_MERGE=false` to audit external
contributions without granting the automation mutation authority over them.

**Large or generated changes.** Lower file/line ceilings to route unusually
large PRs to humans even when CI and reviews pass.

**Incident mode.** Set mode back to `observe` or disable
`PR_AUTOMATION_MERGE_WHEN_READY`; the status/index continues working while all
automatic mutation stops.

## Validation

Focused suites:

```bash
python -m pytest -q \
  skeleton/testing/test_pr_automation.py \
  skeleton/testing/test_pr_automation_ruleset.py
```

Coverage includes deterministic decisions, future GitHub merge states, CI
reruns/provider collisions, skipped/neutral checks, stale approvals, active
change requests, fork/deleted-head behavior, thread uncertainty, scope limits,
index deduplication/tamper detection, failed-action retry, run-wide mutation
budget, full apply revalidation, protected-base enforcement, expected-head
merges, and ruleset payload invariants.
