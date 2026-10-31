# POSIX token-spool ancestor and selected-source custody

LongContextSpool now traverses every POSIX ancestor from the filesystem
anchor using held directory descriptors and O_DIRECTORY|O_NOFOLLOW.
Creation of the root, objects and checkpoints is descriptor-relative.
A symlink substituted at any ancestor cannot redirect a later write to
an attacker-controlled directory. The final pinned root remains valid
when a path is renamed, and no existing checkpoint is overwritten.

The installed long-context CLI uses the same no-follow ancestor walk for
selected token-sequence input. It checks a regular-file descriptor and
enforces the serialized byte limit before parsing. On Windows, path-based
fallback remains explicitly unqualified against same-user ancestor races;
this is not a claim of a native handle-relative Windows security boundary.
The spool still requires trusted checkpoint digest custody for rollback
detection and does not serialize model KV tensors.
