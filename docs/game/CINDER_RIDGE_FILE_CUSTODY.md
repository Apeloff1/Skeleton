# Cinder Ridge bounded file custody

The CLI now opens every ancestor through directory file descriptors with
`O_DIRECTORY | O_NOFOLLOW`, rejects parent symlinks and traversal components,
and opens final input files with `O_NOFOLLOW`. Inputs must be regular files
within the caller's byte budget and stable throughout the read. FIFO reads are
nonblocking and rejected before consuming input.

Exports are written to a restrictive 0600 temporary inode in the pinned parent
directory, synced, and atomically hard-linked to the final filename. A final
filename that already exists is never replaced. A failed publication removes
only the temporary inode, subject to inode identity verification; it never
unlinks the requested destination. This prevents partially written final
exports from being mistaken for completed saves.

On systems without POSIX no-follow and dirfd capabilities, the CLI explicitly
refuses filesystem IO. This is a fail-closed platform limitation, not Windows
qualification. Windows consumer delivery requires a separately reviewed
reparse-point-safe native file API implementation.

The protection is against path substitution, not malicious modification by
a process that already holds a writable descriptor to the same input inode.
Canonical replay validation still rejects corrupted or inconsistent game state.
Focused regression tests cover symlink ancestors, final symlinks, traversal,
FIFO, byte bounds, overwrite, publication failure, permissions and cleanup.
