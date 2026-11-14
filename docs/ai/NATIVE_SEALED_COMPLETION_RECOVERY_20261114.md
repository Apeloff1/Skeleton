# Native sealed completion and session custody

Recovery requires the independently signed approval for the exact current
generation and lease, the already anchored scheduler state and bound journal.
For a whole-request native owner, an authenticated AES-GCM result may establish
completion even if the journal was left RUNNING by a crash after vault COMMIT.
The original intent must match the permit. Ciphertext, nonce, AAD, token count
and model binding are checked without returning plaintext. The journal commits
the terminal receipt before the session acknowledges it. A corrupt or missing
result, missing intent, legacy partial lease or stale approval is not repaired.
A crash after receipt COMMIT can repeat the verified recovery without executing
the model. It cannot repeat after the session advances.

A private session opener retains its exact handle and validates it before
reads and commits. Native composition refuses shared connections and, when
the scheduler has a private handle, shared inodes. Legacy trusted-connection
constructors remain explicitly unqualified. The status reports restart-lost
pending leases as uncertain. External-anchor divergence, hard process
termination, Windows custody and real-device qualification are outside this
repair.
