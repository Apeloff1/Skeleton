# POSIX spool publication inode fencing

A long-context content-addressed token object is not trusted merely because its final pathname exists. Under the bounded publication lock, the writer verifies its private temporary file's descriptor, named inode, owner, mode, link count and exact size before linking. After link creation it verifies that the final name still refers to the same writer inode and that the expected two links exist. The temporary name is revalidated before cleanup; a replaced name is not blindly unlinked. Both publication and unlink phases synchronize the bucket directory.

These checks reduce same-UID name-swap and partial-publication risks, but do not claim protection against an adversary with arbitrary same-UID write authority over the spool directory. Digest verification, bounded recovery, trusted checkpoint anchors, OS process isolation and external authorization remain necessary. No GPU, M-chip or device qualification is implied.

Focused test: `python -m pytest -q tests/flgb/test_long_context_spool.py`. Required exact-head CI/security and release holds remain in force.
