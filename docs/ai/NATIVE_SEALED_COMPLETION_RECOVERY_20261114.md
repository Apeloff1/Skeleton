# Native sealed completion and session custody

Recovery requires the independently signed approval for the exact current
generation and lease, the already anchored scheduler state and bound journal.
For a whole-request native owner, an authenticated AES-GCM result may establish
completion even if the journal was left RUNNING by a crash after vault COMMIT.
The original intent must match the permit. Ciphertext, nonce, AAD, token count
and model binding are checked without returning plaintext. The journal commits
the signed execution receipt before the session acknowledges it. A corrupt or missing
result, missing intent, legacy partial lease or stale approval is not repaired.
A crash after receipt COMMIT requires the distinct committed-receipt recovery
approval and verification of the bound vault; never execute the model again.
Recovery cannot be repeated after the session advances.

A private session opener retains its exact handle and validates it before
reads and commits. Native composition refuses shared connections and, when
the scheduler has a private handle, shared inodes. Legacy trusted-connection
constructors remain explicitly unqualified. The status reports restart-lost
pending leases as uncertain. External-anchor divergence, hard process
termination, Windows custody and real-device qualification are outside this
repair.

Operator recovery must be configured at trusted service composition using a
separate high-entropy recovery key. A request-provided key is checked against
the configured domain-separated commitment before its signed approval is
verified. Without provisioning, all operator recovery fails closed. Invalid
configuration is rejected before creating or bootstrapping custody. Preserve
the same separately managed authority across a restart; no secret is written
into public status or the SQL ledger. The caller remains responsible for
independent operator authentication and exclusive ownership.

Cancellation revokes the process-local grant before retiring canonical state.
For an issued permit, the permanent journal cancellation fence is committed
first; an existing sealed output blocks retirement. A failed cleanup leaves
the pending checkpoint and exact cancellation receipt available for explicit
operator recovery. No repair recreates the revoked plaintext grant.
