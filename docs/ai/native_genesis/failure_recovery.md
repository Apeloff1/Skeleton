# Fail-closed partial materialization and uncertain-training recovery

Genesis publication writes a checkpoint and its matching manifest under
SHA-256-derived names, exclusively and without overwrite. If a crash
happens between the two files, the checkpoint must be treated as
unqualified and the incomplete directory inspected; a retry does not
silently overwrite either file.

A partial trainer run may have created a genesis checkpoint before the
candidate exists. That checkpoint remains a valid initialization artifact
only after re-verifying its manifest, file digest and model identity; it
is not evidence that SGD completed.

The lifecycle has explicit `uncertain` and `held` states. No transition
from an uncertain run to production admission is permitted. Retrying with
the same run identity after an ambiguous side effect is forbidden without
operator reconciliation and a new authorized transaction.

The local process fence excludes concurrent model training on one machine
but is not a distributed lease or CAS authority. External key custody,
audit-head pinning and interhost fencing must be qualified independently
before multi-machine use.

Never weaken source integrity checks, lower security gates, or relabel
cancelled and skipped test runs as success to make publication appear green.
