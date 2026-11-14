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

A startup clock fault before the guard registers the lease requires fresh
authorized composition. Process-identity violations, replay attempts and
exhausted lifetime capacity likewise require fresh composition. The exact
retired lease can reauthorize an inactive, recoverably stopped guard only.

## Provisioning the independent recovery authority

Trusted startup must supply `operator_recovery_key` to the dispatch service
(or `bind_native_cpu_dispatch_service`) from the independently managed
operator secret. Reopening requires re-provisioning the same authorized key.
Omitting it disables all committed, published, cancelled and abandonment
recovery operations; it does not disable ordinary fresh inference. A
request-selected key cannot establish its own trust root. The dispatcher
pins a domain-separated key commitment in memory and checks it before
verifying a scoped approval or using its journal recovery path.

Never reuse the custody key, receipt signing key or result encryption key
as the operator key. Native composition checks the session and journal agree
on the receipt signer and rejects role reuse before binding result custody.
These source checks do not provision secrets, establish independent process
quiescence, qualify a device, or replace external operator authentication.
