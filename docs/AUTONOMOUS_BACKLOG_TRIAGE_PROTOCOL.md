# Autonomous Backlog Triage Protocol

## Purpose

Define deterministic rules for converting repository backlog signals into bounded work units.

## Ordering

1. Restore broken correctness paths.
2. Restore security and policy gates.
3. Remove merge blockers.
4. Improve test coverage around changed behavior.
5. Execute approved capability expansion.

## Work Unit Requirements

Every worker assignment should include:

- immutable base identity
- source evidence
- affected subsystem
- expected validation
- rollback boundary
- completion artifact

## Admission Rules

A task is not actionable because it exists. It must have:

- bounded scope
- registered worker capability
- validation path
- ownership chain

## Failure Handling

Failures become new evidence items. They must not silently retry forever.

Each retry requires:

- classified failure reason
- unchanged authority boundary
- updated attempt identity
- preserved previous evidence

## Completion

A backlog item is considered complete only when:

- implementation exists
- validation evidence exists
- no policy boundary was bypassed
- resulting state is reproducible
