# Immutable spool object hardlink custody

Every immutable token object and checkpoint is now required to have exactly
one filesystem link in addition to private owner/mode checks. A hardlink
outside the spool permits same-UID mutation of an otherwise private inode;
content-addressed digests detect altered bytes later, but do not make that
external mutation acceptable during admission. Both existing-object
idempotency and read/resume fail closed on a multiply linked inode.

Publication still uses a temporary link during the atomic no-clobber
publication sequence, then unlinks the temporary name. A concurrent read
during that short window may conservatively reject the object and must
retry only through explicit caller reconciliation; no implicit generation
replay is permitted. This does not isolate a malicious same-UID process.
