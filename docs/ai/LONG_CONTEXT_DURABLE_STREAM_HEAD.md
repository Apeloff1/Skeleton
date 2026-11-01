# Durable offline long-context stream heads

The existing immutable checkpoint spool allows progress forks. The opt-in
`LongContextProgressHead` adds a **single committed cursor** for each local
stream. This is POSIX-only operator custody, not a GPU/M-chip qualification,
multi-tenant authorization system, model KV snapshot or execution lease.

`head-init --stream-id S --checkpoint D` verifies complete bounded ancestry
and binds a stream to a checkpoint. `head-status --stream-id S` audits the
committed head. `head-window --stream-id S --max-tokens N` observes a bounded
window and checkpoint expectation; it does **not** authorize execution.
After work is actually consumed, `head-advance --stream-id S
--expected-checkpoint D --consumed-tokens N` commits a new immutable child
with compare-and-swap. A concurrent stale worker is rejected and must
discard its work. All commands also require the tokenizer digest and root.

The per-root inode-verified private POSIX flock serializes cooperating head
writers. Descriptor-relative 0700 directories, 0600 canonical JSON, content
digests, 4096-head/8-MiB bounded inventory, disk-reserve checks, O_EXCL
temporary files, fsync and atomic replacement preserve local crash custody.
Unknown telemetry, malformed records, symlinks, untrusted entries, missing
ancestry, forked processes and stale CAS deny progress. Same-UID hostile
writers are outside the trusted operator boundary.

Crash after checkpoint creation but before head replacement leaves an
unreachable immutable child, not acknowledged progress. Crash around fsync
may leave old or new head: always re-read status after ambiguous errors.
`head-recover` explicitly removes only bounded verified orphan head temps.
No arbitrary cleanup or silent checkpoint deletion occurs.

Focused regression target:
`python -m unittest tests.flgb.test_long_context_progress`
and `python -m pytest -q tests/flgb/test_long_context_spool.py`.
Require exact-head CI, security and review before promotion or release.
