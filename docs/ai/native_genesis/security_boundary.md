# Security boundary: offline original model initialization

The initializer does not download, retrieve, introspect, or impersonate any
hosted model. It never resolves named remote providers. It uses the same
native transformer that already exists in Skeleton's `cortex`, constrained
to deterministic seed-based weights.

Inputs are bounded before allocation: seed, tensor dimensions, layer counts,
attention-head geometry, learned or rotary position mode, FFN type, vocabulary
size, optimizer steps, checkpoint bytes, training wall time and batch length.
Booleans are not accepted as integers. Unknown serialized policy keys are
rejected instead of ignored.

All corpus items are original source records with one license and exactly
one training scope, not a rights waiver for arbitrary future data. The
source proof includes exact data coverage, original answer checks, dedup,
held-out isolation and independently scanned benchmark overlaps. Near-
duplicate rights review remains open, even when exact overlap is zero.

No publication call is made during preview, doctor, policy-vector or smoke
mode. Actual publication uses POSIX `openat`-style custody with
`O_NOFOLLOW`, `O_EXCL`, owner-private directory validation, file fsync
and directory fsync. Existing immutable names cannot be reused or replaced
without deliberate operator incident review.

Randomly initialized weights have zero training steps. Successful execution
of a two-token native graph does not imply the generated answer is correct.
Successful SGD changes only a cloned candidate model; it cannot mutate the
champion or authorize an automatic production model pointer update.

The v1 materializer is POSIX-only. Windows or mobile execution, GPU routing,
tensor parallelism, multi-host lease consensus and end-user installs remain
unqualified. Do not interpret CPU reference tests as device certification.
