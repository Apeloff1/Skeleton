# POSIX directory-fd custody hardening

The long-context spool now pins its trusted root directory inode with
`O_DIRECTORY | O_NOFOLLOW` on POSIX. Every object/checkpoint bucket and
content-addressed file is opened relative to pinned descriptors, not by
re-resolving mutable path strings. Publication uses exclusive temporary
creation, fsync, and same-directory hard-link no-clobber. Disk reserve is
observed with `fstatvfs` on the anchored filesystem.

This closes common final-component and bucket replacement symlink races
on POSIX, but the caller must still choose a trusted root parent and protect
directory ownership and permissions. External replacement of the root path
does not retarget the existing instance's file descriptors. Missing POSIX
secure-open primitives fail closed. Windows continues using the legacy
path-based fallback and is **not** certified against concurrent directory
replacement; keep Windows storage qualification on hold pending native
handle-based hardening.

The spool is not a secure key vault, multi-process lease manager, encrypted
storage engine or KV-tensor persistence layer. Original source/tokenizer
identities, bounded size and immutable checkpoint semantics remain intact.

## POSIX private ownership is mandatory

The pinned spool root, objects/checkpoints directories and digest buckets must
be owned by the effective user with mode 0700. Stored immutable token objects
and checkpoint files must be owned by that user with mode 0600, including when
an identical digest already exists or another writer publishes concurrently.
A world-readable file with matching content is not accepted as safe custody.
These checks operate on opened file descriptors, not pathname-only checks.
Windows remains explicitly unqualified for equivalent ACL and ancestor-race
assurance. This does not authenticate a malicious same-user publisher.

## Cooperative disk-reserve serialization

POSIX spool publication now takes a descriptor-relative private `.publish.lock` using a bounded nonblocking advisory `flock`. The lock is held across the free-space admission check, temporary write, fsync, no-clobber hardlink and directory fsync. The lock inode is checked for owner, mode, link count and descriptor-relative identity after acquisition. A busy or replaced lock fails closed; reads do not require publication locks. This prevents cooperating processes from simultaneously spending the same free-space reserve, but does **not** implement a per-tenant total-disk quota or protect against a malicious process running with the same filesystem owner identity. The storage backend must still enforce those limits independently.
