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
