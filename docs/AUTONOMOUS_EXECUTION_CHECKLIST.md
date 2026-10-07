# Autonomous Execution Checklist

## Purpose

Operational checklist for the Supervisor -> Secretary -> Worker pipeline.

## Admission

- [ ] Confirm exact default-branch SHA.
- [ ] Bind snapshot fingerprint to execution identity.
- [ ] Reject stale or replayed custody envelopes.
- [ ] Keep planning authority separate from mutation authority.

## Worker execution

- [ ] Select only registered workers.
- [ ] Require bounded scope and explicit target files.
- [ ] Record start, progress, failure, and completion evidence.
- [ ] Prevent duplicate branches and duplicate pull requests.

## Recovery

- [ ] Classify failures before retry.
- [ ] Retry only transient failures.
- [ ] Stop on policy, permission, or validation failures.
- [ ] Preserve evidence for failed runs.

## Completion gate

A task is complete only when:

1. Changes exist in a reviewable branch or PR.
2. Validation results are attached.
3. Remaining risks are recorded.
4. The next worker can continue deterministically.
