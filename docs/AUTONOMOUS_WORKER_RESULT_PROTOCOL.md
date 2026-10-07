# Autonomous Worker Result Protocol

## Purpose

Define the contract between worker execution and repository orchestration.
The worker reports evidence, not authority.

## Result lifecycle

1. accepted
2. executing
3. blocked
4. completed
5. rejected
6. failed

## Required result fields

- execution identity
- task identity
- changed files
- validation performed
- validation outcome
- failure category when unsuccessful
- reproducible evidence references

## Safety rules

- Results cannot bypass required checks.
- A worker cannot expand its own authority.
- Failed work must produce actionable diagnostics.
- Duplicate executions must converge on one canonical result.

## Recovery handling

Transient failures may retry with bounded attempts.
Deterministic failures require correction before retry.
Repeated failures escalate to investigation state.

## Completion standard

A task is complete only when implementation, validation, and evidence agree.
