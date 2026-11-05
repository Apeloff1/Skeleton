# One-use operator authorization for offline result reads

The result vault stores only AES-GCM ciphertext and immutable model/tokenizer
bindings. The journal independently authenticates completed execution. This
component adds a **third** private SQLite database to consume one-use operator
read grants, preventing a read capability from being silently replayed after
restart. A failed decrypt burns the grant; no automatic retry occurs.

The trusted operator signs a canonical, bounded `result-read-grant.v1`
message using Ed25519. The app pins the corresponding 32-byte public key and
never stores the private signing key alongside inference data. A grant binds
session, generation, checkpoint, lease, signed result digest and a unique
16-byte random nonce. The operator authenticates the user and chooses the
nonce. No clock or unreliable wall-time expiry is treated as a replay fence.

`AuthorizedSealedResultReader.read_once` first verifies the journal's signed
completion receipt, then the operator signature, and atomically consumes the
nonce before decrypting. The app must separately enforce user authorization,
key provenance, physical filesystem custody, external rollback protection and
result retention/deletion. A restored older grant ledger can permit replay;
do not treat this SQLite table as a trusted anti-rollback device.

Wire the reader to the same journal and vault as
`JournaledExecutionOwner(journal, vault)`, with a distinct
`open_private_sqlite(..., filename="grant.db")` handle. The app may expose
a separately authenticated local-only read operation; this change deliberately
adds no public HTTP route or unqualified device claims.

Run `python -m pytest -q skeleton/testing/test_fair_stream_result_access.py`
alongside the result-vault, journal and private-SQLite tests. Exact-head
security and integration CI remain release prerequisites.
