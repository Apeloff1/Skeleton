# Bounded long-context spool crash recovery

A process may crash between fsync, link publication, and removal of its
temporary file. The POSIX token spool now recovers only temporary names
belonging to a known content digest, while holding its existing cooperative
cross-process publication lock. This is also invoked automatically before a
new publication of that digest.

The recovery validates the descriptor-pinned bucket, exact temporary name,
owner, 0600 mode, regular-file type, size, link count and inode identity. A
single-link interrupted temp can be deleted; a two-link published temp can
be removed only if its second link is the canonical digest name. Unexpected
links, symlinks, changed inodes, excess entries, excess bytes or unreadable
directory metadata fail closed. Unlink is followed by bucket fsync.

The scan is bounded (4096 entries), the number of candidate temp files is
bounded (64), and the total candidate byte budget is bounded (128 MiB).
No user-selected wildcard cleanup, automatic retry of uncertain inference,
trusted publisher claim, or Windows filesystem qualification is implied.
