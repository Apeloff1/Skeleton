# Explicit uncertain native execution abandonment

This maintenance seam retires one irrecoverable pending native request without
claiming success, deleting output, or retrying it. Stop all former execution
owners and independently establish quiescence. Review the exact anchored
pending lease and absence of a published output; sign the dedicated
abandonment authorization with the separately configured recovery key and a
digest of the reviewed evidence. A normal completion approval is not valid.

The bound private journal retains a signed abandonment payload in its RUNNING
row (or creates a replay tombstone if no intent was recorded). The legacy state
label intentionally remains RUNNING, but its non-null receipt prevents later
completion; normal result reading requires COMMITTED. The authenticated
scheduler consumes a distinct abandonment receipt, removing only that request.
If the journal commit succeeded before the custody transition failed, retry
only the same approval after trusted anchor reconciliation. No backend runs.

This is not proof that the old worker stopped, an anti-rollback anchor, or an
automatic abandonment policy. The signed evidence attests an independently
reviewed operational condition. All previous owners must be quiescent; an
existing encrypted output always blocks this path, even if corrupted.

After authenticated retirement and journal tombstone verification, the bound
CPU owner may release its stopped pressure guard for the exact inactive lease.
Used lease identities remain retained, epochs invalidate old callbacks, and
new requests still require independent live OS pressure sampling. A failed
anchor transition continues to fence dispatch. This is not hardware recovery
or automatic restart authorization.

A startup clock fault is now attributed to the exact attempted lease before
any callback is issued. Its identity is burned and can be retired by the
same operator procedure. Process-identity violations, replay attempts and
exhausted lifetime capacity require fresh authorized composition instead of
releasing the guard with an unrelated or previously successful lease.
