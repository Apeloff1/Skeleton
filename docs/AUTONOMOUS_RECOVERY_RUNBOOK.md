# Autonomous Recovery Runbook

## Purpose

Define bounded recovery behavior for the Supervisor -> Secretary -> Worker automation chain.

## Failure classes

- Admission failure: reject execution and preserve evidence.
- Stale custody: stop mutation when the observed base SHA no longer matches.
- Provider failure: retry only bounded transient failures.
- Worker failure: record terminal state and avoid duplicate fanout.
- Publication failure: preserve branch and evidence for recovery.

## Recovery rules

1. Never bypass validation gates.
2. Never mutate main directly from automation.
3. Reuse existing custody identity when retrying.
4. Prefer convergence over spawning parallel duplicate work.
5. Emit terminal evidence for every admitted run.

## Operator checklist

- Verify base SHA.
- Verify delegation fingerprint.
- Verify worker authorization.
- Verify validation evidence.
- Verify resulting PR or terminal failure reason.
