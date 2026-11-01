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

## Generation-fenced observation and commit (opt-in)

The existing `head-window` and `head-advance` remain backward-compatible.
For cooperating operators that need a precise checkpoint/generation/window
binding, use `head-compare-window --stream-id S --expected-checkpoint D
--expected-generation G --max-tokens N`. This acquires the same private
cross-process lock, audits the entire bounded ancestry, and checks the head
before and after reading. The returned window digest covers exact token IDs,
start, stop and source-sequence digest. Exhausted windows return null.

Only **after** an independent trusted execution owner durably proves that
the backend actually consumed tokens, invoke `head-commit-window --stream-id S
--expected-checkpoint D --expected-generation G --expected-window-digest W
--max-tokens N --consumed-tokens K`. It verifies the *same* window under
the head lock, refuses stale generations, changed token windows, exhausted
streams, oversized consumption, malformed inputs and broken ancestry. A
successful commit creates an immutable child and fsyncs the new CAS head.
If publication is ambiguous, inspect status; NEVER blindly retry execution.

Neither observation nor commit is an execution authorization, an HMAC
publisher identity, an external anti-rollback fence, or an exactly-once
backend guarantee. A crash after irreversible model work but before the
external execution journal's durable completion must remain UNCERTAIN.
Do not infer successful consumption from a window digest alone.

## Read-only whole-root recovery audit

`head-audit --max-heads 64 --max-checkpoints 4096` checks every
committed stream head in the private POSIX directory under the same
cross-process custody lock, with a strict 262,144-checkpoint work ceiling.
It verifies inventory type, owner, mode, link count, canonical head records,
tokenizer identity and complete bounded ancestry before reporting success.
If a head count exceeds the supplied limit, a checkpoint is missing, any
entry is malformed, or the audit exceeds the work ceiling, it fails closed.
It does not delete, repair, advance, replay or publish any state.

Output contains only aggregate head count, bounded inventory bytes, orphan
temporary count and canonical aggregate digest. No stream IDs, token IDs,
plaintext prompts, keys, model weights or checkpoint payloads are returned.
The digest is **not** a MAC, proof of trusted publisher identity, or an
external rollback fence. Different tokenizer identities in one root are
rejected; keep separate roots per tokenizer/operator trust domain.
