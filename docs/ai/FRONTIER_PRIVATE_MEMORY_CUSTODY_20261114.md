# Private Frontier memory storage

Use `SQLiteCollection.from_private_database(directory, create=True)` only for explicit
first initialization, and reopen with `create=False`. The caller must provide an already
existing owner-only absolute directory. The collection owns the handle and serializes
worker-thread database access. Before reads and mutations it checks directory permissions,
inode identity, database attachment and page budget. Writes use explicit transactions.

The existing path constructor remains a compatibility seam for local development and
migration. Do not claim it is private storage; move production callers to the explicit
private constructor after migration and device qualification. The main-file page cap
does not reserve physical disk or constrain all temporary journal bytes. Same-UID races,
storage encryption, and Windows/WSL2 private-file custody remain separate qualification.
