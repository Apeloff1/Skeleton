# PR automation index

`Skeleton` PR automation is a fail-closed control plane for evaluating pull
requests and, when explicitly enabled, merging only a head SHA that has already
passed the configured policy.

## Safety model

The privileged workflow uses `pull_request_target`, but it always checks out
the repository default branch. It never checks out, imports, or executes code
from a pull request head. Fork PRs are observe-only unless an owner explicitly
opts in.

Evaluation and mutation are separate. The policy engine produces an immutable
plan bound to the observed head SHA. Apply mode re-fetches the PR immediately
before mutation and the GitHub merge request includes the same SHA as an API
precondition. A synchronized commit therefore invalidates the plan instead of
being merged accidentally.

The engine fails closed on:

- draft, closed, merged, conflicting, blocked, behind, or unknown merge state;
- missing, pending, failing, unknown, or incompletely paginated CI state;
- incomplete approval history or insufficient approvals;
- unknown or unresolved review threads;
- fork PRs unless explicitly allowed;
- unsupported base branches;
- invalid or oversized change metrics;
- stale head SHA between evaluation and mutation;
- event-index hash-chain corruption;
- mutation caps, invalid configuration, rate limits, and API failures.

Apply mode is deliberately harder to enable than observe mode. When
`PR_AUTOMATION_REQUIRE_CHECKS=true`, merge apply mode refuses to start unless
`PR_AUTOMATION_REQUIRED_CHECKS` names the exact checks that must pass.

This system complements branch protection and repository rulesets; it does not
replace them.

## Event index

`.pr-automation/index.sqlite3` is restored and saved through a serialized
Actions cache. The workflow also exports `.pr-automation/index.jsonl` as a
human-readable artifact.

The SQLite index provides:

- append-only evaluation/action events;
- SHA-256 hash chaining per PR for tamper evidence;
- policy and snapshot fingerprints;
- state-transition deduplication across repeated schedules;
- an atomic latest-state materialization;
- action idempotency claims with retryable failed attempts and stale-claim
  recovery;
- WAL, full synchronous writes, busy timeouts, and one-writer workflow
  concurrency.

Repeated observe runs on an unchanged PR do not grow the event stream. A policy
change creates a different policy fingerprint and therefore a new auditable
event even when the PR snapshot is unchanged.

## Configuration

Repository variables control behavior:

| Variable | Default | Purpose |
| --- | --- | --- |
| `PR_AUTOMATION_MODE` | `observe` | `observe` or `apply` for non-manual runs |
| `PR_AUTOMATION_ALLOWED_BASES` | `main` | Comma-separated eligible base branches |
| `PR_AUTOMATION_REQUIRED_CHECKS` | empty | Exact comma-separated required check names |
| `PR_AUTOMATION_REQUIRED_APPROVALS` | `0` | Minimum current approvals |
| `PR_AUTOMATION_REQUIRE_CHECKS` | `true` | Require a known passing CI state |
| `PR_AUTOMATION_REQUIRE_RESOLVED_THREADS` | `true` | Require all visible review threads resolved |
| `PR_AUTOMATION_ALLOW_FORK_MERGE` | `false` | Allow merge actions for fork PRs |
| `PR_AUTOMATION_MERGE_WHEN_READY` | `false` | Plan/execute a merge after all gates pass |
| `PR_AUTOMATION_MERGE_METHOD` | `squash` | `merge`, `squash`, or `rebase` |
| `PR_AUTOMATION_MAX_CHANGED_FILES` | `250` | PR scope ceiling |
| `PR_AUTOMATION_MAX_LINE_DELTA` | `20000` | Additions + deletions ceiling |

`PR_AUTOMATION_MAX_MUTATIONS` is fixed to `1` in the workflow. This keeps each
evaluation cycle bounded even if future policy adds more action types.

A manual dispatch can override execution mode for one run and can target one PR
number. Scheduled runs scan at most 25 recently updated open PRs.

## Failure and recovery behavior

Transient GitHub 429/5xx/network errors are retried with bounded backoff.
Pagination is capped; if the cap is reached before all check runs or reviews
are collected, the state becomes unknown and merge is held.

Action claims are written before mutation. Successful claims are never
re-executed. Failed claims are retryable. In-flight claims can be reclaimed
after a timeout so an interrupted runner cannot permanently wedge a PR.

A merge request uses GitHub's `sha` precondition. Even if the head changes in
the narrow interval after the final re-fetch, GitHub rejects the merge rather
than applying the old decision to new code.

## Focused validation

`python -m pytest -q skeleton/testing/test_pr_automation.py`

The regression suite covers deterministic decisions, policy fingerprinting,
CI aggregation, latest-review semantics, fork/draft/conflict/stale handling,
scope ceilings, event deduplication, hash-chain tamper detection, idempotent
action claims, retryable failures, JSONL export, and expected-head merge
preconditions.
