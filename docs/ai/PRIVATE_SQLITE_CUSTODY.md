# Private SQLite custody bootstrap (POSIX)

`open_private_sqlite(directory, create=...)` is a fail-closed bootstrap helper
for the existing canonical `DurableFairStreamStore`. It never provisions keys
or an external anti-rollback anchor. The app must create a private owner-owned
directory with mode 0700 **before** invoking it, and must keep that directory
unshared with other processes running as the same UID.

The opener traverses path components with dir-fd/O_NOFOLLOW, rejects directory
symlinks, group/other-accessible final directories, hardlinked or incorrectly
permissioned files, and refuses implicit creation on restart. It opens SQLite
in `mode=rw`, checks that the backing inode is unchanged, sets durable DELETE
journal/FULL synchronous mode, disables trusted schema, performs a quick
integrity check, and limits the main database to a configured page budget.
The returned `PrivateSQLiteHandle` must remain alive for the session lifetime
and must be closed by the app. This does **not** bound journal/snapshot usage;
the app must independently reserve disk space and apply total storage quotas.

`OfflineAdaptiveDispatchService.from_private_database(...)` returns
`(service, handle)`, never a hidden owned handle. On bootstrap failure the
connection is closed. A restart uses `bootstrap=False` and requires the
**same independent durable** high-watermark. A database and its anchor cannot
be stored together and called rollback-resistant. SQLite is not a key vault.

The implementation intentionally fails closed on Windows or POSIX platforms
without required openat/O_NOFOLLOW facilities. This is not an Apple Silicon,
Metal, GPU, encrypted-disk, multi-process isolation, or physical memory
qualification. Tests are synthetic and verify only the documented bootstrap
and filesystem checks. No automatic pending-lease re-execution is introduced.

## Descriptor-pinned execution journal

The native app binder now requires a second `PrivateSQLiteHandle` for the
execution journal, distinct from the encrypted result database handle. It
checks the exact journal SQLite connection, descriptor-backed inode,
directory ownership, file permissions, attachment identity and byte budget.
The journal binds this handle once and revalidates it before each durable
intent transaction and receipt read. Path replacement after initial binding
is therefore a hard failure before native execution, not an opportunity to
silently recreate a journal. A compromised same-UID process remains outside
this primitive's threat model; the app must isolate accounts and preserve
exclusive handles, external rollback anchors and bounded disk custody.
