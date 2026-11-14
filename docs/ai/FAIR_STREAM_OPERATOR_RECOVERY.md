# Explicit offline fair-stream committed-result reconciliation

A backend result can be durably published and its execution-journal receipt
committed while the caller loses the response before the canonical custody
generation advances. The system must **never** execute that lease again merely
because the app restarted. This recovery seam permits one explicit operator-
approved reconciliation of an independently authenticated committed receipt.

## Boundaries

* The app validates the independent custody high-watermark before reading
  the pending lease. Missing, rolled-back or mismatched state quarantines.
* The caller provisions an independent 32–128-byte recovery key through a
  trusted operator interface. The key is not stored in SQLite or serialized.
* The operator issues a 128-bit nonce and signs the **exact** session,
  generation, checkpoint digest and lease ID. Grants cannot authorize future
  generations, another session or a different pending lease.
* Only the canonical execution journal can return the already-committed
  receipt. A RUNNING journal intent or missing/tampered receipt is a hard hold.
* The canonical session verifies the execution MAC and advances its own
  SQLite custody and independent monotonic CAS. If this transition fails,
  quarantine remains in force and no backend retry is attempted.
* The application exposes a separate `reconcile_committed` method. Startup,
  `status`, and `execute_next` never auto-reconcile or mint grants.
* The recovery API is a trusted in-process administrative seam, **not** an
  HTTP endpoint, CLI with embedded keys, a device attestation or a way to
  recover from a missing independent anchor. A compromised same-UID process,
  key vault failure or malicious database owner is outside this guarantee.

## App integration

The trusted operator obtains the pending custody state from the already
authenticated session, issues an approval using
`issue_recovery_authorization`, and calls
`OfflineAdaptiveDispatchService.reconcile_committed(journal=...,
authorization=..., recovery_key=...)`. The journal must be separately
opened, owned and exclusive; it must hold the signed receipt for the same
lease. The result is a payload-free `OfflineDispatchStatus` object.

The app should show a **manual reconciliation required** hold for pending
leases on restart. A missing receipt is an unresolved execution outcome,
not an invitation to retry. Repeated operator grants cannot retire an
already-acknowledged lease because the signed custody generation advances.

## Deterministic coverage

`python -m pytest -q skeleton/testing/test_fair_stream_recovery.py`
covers restart, lost response, independent operator MAC, cross-session
rejection, unknown RUNNING intent, forged journal receipt, replay and
high-watermark divergence. These are simulated CPU-only tests and do not
certify hardware, power management or on-device inference.
