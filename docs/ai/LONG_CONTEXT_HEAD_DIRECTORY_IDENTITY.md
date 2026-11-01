# Durable stream-head namespace fencing

The POSIX head CAS lock now checks that the pinned `heads` directory and
`.heads.lock` inode still occupy their expected descriptor-relative names
before and after every head operation. A renamed directory must never produce
a successful cursor receipt for an invisible old namespace. A replaced lock
must never silently serialize unrelated cooperating writers.

Checks cover owner, mode, file type, inode and link count; errors fail closed.
Post-operation mismatch is an **ambiguous commit**: inspect the actual
durable head before any retry, never replay irreversible inference solely
because an acknowledgement failed. This is cooperative local custody and
does not promise isolation against an adversarial same-UID writer.

Focused validation on POSIX:
`python -m unittest tests.flgb.test_long_context_head_directory_identity -v`
and `python -m unittest tests.flgb.test_long_context_progress -v`.
Exact-head CI, storage fault injection and independent review remain release
holds; neither a head status nor an observed window grants execution authority.
