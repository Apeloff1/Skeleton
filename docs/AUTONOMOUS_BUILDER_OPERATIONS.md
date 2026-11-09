# Autonomous Builder Operations

This runbook closes the operator-facing contract for the scheduled
Traffic Manager → Supervisor → Secretary → feature-builder path.

## Authority and custody

The Traffic Manager is read-only admission control. A scheduled or manually
forced admission captures the exact default-branch SHA, re-reads the live
default-branch head immediately before dispatch, and coalesces the dispatch if
that SHA became stale. The admitted SHA is passed to the reviewed Supervisor
workflow as `expected_base_sha`.

The Supervisor is a read-only planner. It seals repository, base SHA, snapshot
fingerprint, workflow execution identity, and any maintainer-approved build
authorization into the delegation envelope. The Secretary is the only
delegation boundary. It revalidates custody before dispatch and routes an
authorized build to `feature-builder` without relying on model keywords.

The feature builder receives a deterministic Builder Plane manifest binding the
approved issue, task digest, snapshot, execution, base SHA, budget, stages, and
acceptance evidence. Its branch identity is derived from immutable base/task
custody, so repeated execution converges instead of creating branch fanout.
Workers propose through ordinary pull requests; required CI/security gates
remain authoritative.

## Required configuration

Routine execution requires GitHub Actions plus the repository-scoped token
permissions declared by the reviewed workflows. Model configuration is
optional for planning: `MODEL_API_URL`, `MODEL_NAME`, and `MODEL_API_KEY`
may be supplied, while deterministic planning remains the fallback.

A build requires an open issue carrying an approved build label such as
`build-approved`. Removing that authority or closing the issue prevents a new
authorized feature build.

## Safe operation

Normal operation uses the ten-minute Traffic Manager schedule. For an operator
test, dispatch **Automation Traffic Manager** with `force=true`. Force bypasses
only soft cooldown/no-demand suppression; hard capacity, exact-head custody,
authorization, and downstream validation remain fail-closed.

Do not dispatch Secretary directly to manufacture build authority. Do not edit
workflow permissions, bypass checks, force-push a worker branch, or merge a
worker PR before its required exact-head gates succeed.

## Outcomes and evidence

Operators should distinguish these states rather than treating every no-PR run
as equivalent:

- `capacity-suppressed`: runner/critical-workflow pressure prevented admission.
- `missing-demand`: no eligible approved repository work was admitted.
- `provider-failure`: an external model/provider operation failed; deterministic
  fallback or bounded recovery applies where the contract permits it.
- `stale-custody`: default-branch, snapshot, execution, authorization, or
  manifest custody changed and execution stopped.
- `validation-failure`: proposed work did not satisfy focused validation or
  evidence policy.
- `publication-failure`: validated proposal evidence existed but branch/PR
  publication did not complete.
- `pull-request-created` / `pull-request-updated`: publication succeeded and
  the PR URL is the durable review surface.
- `existing-pr`: deterministic convergence found the already-published worker
  PR rather than creating another.
- `no-change`: admitted work produced no repository mutation.

Worker failures are classified by the closed vocabulary in
`skeleton/automation/execution_failsafe.py`. Only explicitly retryable
pre-execution setup failures receive bounded retry, and retry identity is bound
to the same snapshot/execution custody.

## Recovery and shutdown

For transient setup/provider trouble, allow the bounded retry policy to finish
before manually redispatching. For stale custody, run a fresh Traffic Manager
admission against current `main`; never reuse the old envelope. For validation
failure, repair the implementation or tests and create fresh evidence. For
publication failure, verify repository permissions and GitHub availability,
then redispatch under the same still-valid approved issue; deterministic branch
identity prevents duplicate PR fanout.

To stop new autonomous builds, remove the build-approval label or close the
approved issue. To stop routine admission entirely, disable the Traffic Manager
schedule through repository administration. Existing pull requests remain
ordinary review artifacts and must still satisfy repository merge policy.

## Closure verification for issue #1685

The focused regression contract in
`tests/test_autonomous_builder_e2e_contract.py` verifies scheduled admission,
exact-head dispatch binding, deterministic authorized feature routing, the
Supervisor/Secretary permission boundary, and this terminal-state runbook.
Existing Builder Plane, Supervisor, Secretary, traffic-manager, retry, custody,
and worker-evidence suites provide the lower-level behavioral coverage.
