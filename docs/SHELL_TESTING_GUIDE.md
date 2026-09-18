# Shell Testing Guide

## Purpose

Shell tests protect authority boundaries and stale-state invariants.

The canonical gate runs every file matching skeleton/testing/test_shell_*.py.

That glob appears in the dedicated shell regression gate and again in backend
security regressions.

## Test categories

Runner tests cover argv semantics, environment, cwd, stdin, timeout, output
limits, return codes, and child termination.

Executor tests cover capabilities, argument policy, workspace, retries, circuits,
audit, telemetry, receipts, hooks, and sessions.

Control tests cover cancellation, deadlines, concurrency, leases, command
budgets, feature gates, namespaces, approvals, maintenance, and service state.

Evidence tests cover receipt chain, HMAC attestations, replay, cache, history,
events, traces, failures, incidents, and snapshots.

Worker tests cover identity generations, heartbeat sequences, queue claims,
recovery, supervision, fairness, capacity, admission, topology, failover, and
shutdown.

## Hostile argv

Keep literal shell metacharacter tests.

Include semicolon, pipe, ampersand, redirects, dollar substitution, quotes,
newlines, wildcard, and option-like strings.

Expected behavior is literal argv.

## Environment

Test unknown key denial, value rule denial, required keys, fixed keys, inherited
keys, NUL values, byte limits, and defensive copying.

## Paths

Test cwd escape, nested allowed cwd, missing directory, symlink behavior where
platform stable, and resolved root containment.

## Input and output

Test exact byte boundaries and one-byte-over boundaries.

Test combined stdout and stderr budget.

Test output flood termination.

Test bounded stdin round trip.

## Timeout

Use short deterministic child sleeps.

Avoid long tests.

Verify timeout flag and child termination.

## Stale token pattern

For every renewable or transferable token test:

- current token succeeds
- renewal creates new revision
- old token cannot mutate new state
- expiry invalidates
- reacquisition creates new identity where applicable

Apply to leases, assignments, ownership epochs, approvals, queue claims, and
state revisions.

## Generation pattern

For worker identity test:

- generation one accepted
- generation two replacement accepted
- generation one heartbeat rejected
- generation one unregister rejected
- generation one protocol message rejected
- new generation may restart local sequence

## Receipt tamper

Modify receipt hash or previous hash after append.

Verification must fail.

Do not add repair behavior to verification tests.

## Attestation tamper

Change payload, digest, signature, algorithm, or key ID.

Verification must fail.

## Plan tests

Test empty plan, duplicate ID, unknown dependency, self dependency, cycle,
topological order, failed dependency skip, continue-on-failure, cancellation,
and stable fingerprint.

## Policy change tests

Test compare-and-swap conflict, revision history, migration widening,
migration narrowing, canary zero, canary hundred, rollback, and complete state.

## Output retention tests

Test public retention, internal truncation, sensitive no-byte retention, secret
no-byte retention, item capacity, byte capacity, replacement accounting, expiry,
and pruning.

## Service integration

Use sys.executable for real child execution.

Keep commands tiny.

Examples print constant, exit with code, or short sleep.

Do not depend on external network.

## Deterministic clocks

Inject list-backed monotonic clocks for expiry tests.

Do not sleep in unit tests when a clock can be injected.

## Concurrency tests

A minimal real thread test can verify blocking release.

Keep timeout bounded.

Prefer nonblocking permit tests for most cases.

## Error leakage

Tests should put recognizable secret marker in child output and assert broad
exceptions or metadata do not contain it.

## Cardinality

Every bounded registry should have capacity tests.

Every ring or history should have eviction or exhaustion tests.

## CI performance

Keep shell unit tests stdlib-only where possible.

Avoid network and external services.

Avoid large output unless testing output limiter.

Use small maximums.

## New module checklist

Add happy path.

Add invalid constructor values.

Add exact boundary.

Add stale token.

Add capacity.

Add defensive-copy case.

Add deterministic ordering.

Add serialization shape.

Add security failure path.

Add interaction with adjacent component.

## Principle

A shell test should prove not only that allowed work succeeds, but that stale,
oversized, widened, replayed, or malformed authority fails before it becomes a
host process.
