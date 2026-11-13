# Studio A — Bounded narrative context custody and replay

This vertical provides a real, private author-note workflow: an operator
creates a canonical world, creates a source-leased context journal, appends
original notes under an optimistic hash-head lease, reviews the journal,
compiles a source-bound playable handoff, and verifies its artifacts.

This is **not** model-state serialization, hidden reasoning retention,
provider prompt capture, authenticated signing, or a guarantee of zero context
loss. It is deliberately limited to explicit operator-authored narrative notes.
Never put credentials, system prompts, private chain-of-thought, or secrets in
this journal. The unkeyed SHA-256 chain detects modification but does not
establish identity or prevent a privileged writer from replacing the journal.

## Operator workflow

```sh
python -m skeleton world-context --store PRIVATE create --world-id island
python -m skeleton world-context --store PRIVATE status --world-id island
python -m skeleton world-context --store PRIVATE editor --world-id island \
  --expected-head HEAD_FROM_STATUS
python -m skeleton world-context --store PRIVATE append --world-id island \
  --operation-file island.context.append.json
python -m skeleton world-context --store PRIVATE inspect --world-id island
python -m skeleton world-context --store PRIVATE compile --world-id island \
  --expected-head NEW_HEAD
python -m skeleton world-context --store PRIVATE verify --world-id island
```

The offline CSP-hashed editor contains only the world ID, digest, head and
allowed note kinds. It exports a typed request, never modifies custody. The
CLI requires the current head and strict JSON with no duplicate keys, no
nonfinite numbers and no unbounded input. All writes use descriptor-anchored
world locks and fsynced replacement; source files are regular-file checked,
size-bounded and opened with `O_NOFOLLOW`.

## Deterministic replay and handoff

The journal has monotonically increasing sequence numbers and a hash chain
bound to the exact canonical world digest. Each append validates and replays
the entire bounded chain (128 entries, 2048 characters each). A world revision
invalidates the lease. A stale head fails without overwriting newer notes.
The read-only typed Jeeves tool `context.status` returns metadata only; it
never returns private note text.

Compilation publishes the canonical HTML5 playable, a typed handoff manifest
containing entry hashes and kinds **without private text**, and a last-written
receipt. Verification rereads and recompiles from current sources, rejecting
tampering, missing artifacts, partial writes, stale worlds and forged receipts.
This is a source-integrity handoff, not device/release certification.

Run `python -m pytest skeleton/testing/test_jeeves_world_context_journal.py -q`
on the exact head and then all canonical Jeeves world, security and CI gates.
