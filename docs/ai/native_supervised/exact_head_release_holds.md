# Security, recovery and exact-head qualification holds

Training output is a candidate-only artifact stored under immutable
SHA-256 derived names in a private owner-controlled POSIX root.
Descriptor-based custody rejects symlink traversal and hardlink
aliasing. Content and manifest are separate immutable files; a crash
between their publication must be treated as an incomplete held state.

The synchronized local training fence prevents concurrent trainers
from updating the same native candidate lineage. It is not a
distributed lease or multi-host consensus mechanism. Unknown or
partially committed side effects do not automatically retry.

The training ledger binds source, plan, actual native updates,
validation measurements, model and tokenizer digests, candidate
bytes and evidence. A hash chain without an externally anchored
head cannot by itself prove that a final tail was not deleted.
Independent recovery and key custody must preserve that distinction.

Four authority roles are intentionally separate: trainer,
evaluator, rollback verifier and release officer. A trainer's
approval to produce a candidate cannot authorize serving, merging
or release. Evaluation scores cannot rewrite source rights.

Required final-head checks include Merge Readiness, Backend Quality,
App Foundation E2E, Workflow Input Security, Sealed Context Guard,
Malware Gate, Artifact Policy, Repository Hygiene, Secret Scanning
and Dependency Review. Additional real model qualification, clean
installer, target-device execution, replay and rollback evidence
remain necessary.

A pass on an ancestor commit does not certify a changed child head.
Pending, failed, cancelled, skipped and superseded tests are not
passes. The PR remains draft and release-held until all required
evidence is independently verified on the actual final commit.

Large diff counts are delivery inventory, not functional test results.
A fully written source tree is not a claim that a full SGD job,
all 768 native generations, clean installation or production release
has already been executed.
