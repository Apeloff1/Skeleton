# Immutable long-context object reads: inode and metadata fencing

The POSIX token spool now validates both its open descriptor and its
descriptor-relative digest name after reading an immutable checkpoint or token
object. It compares device/inode, owner, mode, link count, byte length,
modification time and change time, and rejects short or over-budget reads.
The same helper is used when an already-published object is reused and when
another cooperative writer wins an exclusive publication link.

This guards against accidental concurrent replacement and detects many
same-UID name/content races. It does **not** claim adversarial same-UID isolation:
an operator must own the private spool directory, enforce tenant quotas, and
keep execution authority separate from an observed token window. The reader
never grants a backend lease, GPU qualification, or permission to replay an
ambiguous execution after a crash.

Focused validation (POSIX): `python -m unittest tests.flgb.test_long_context_stable_reads -v`
and `python -m unittest tests.flgb.test_long_context_spool -v`. Final-head
required CI and security checks remain mandatory before promotion or merge.
