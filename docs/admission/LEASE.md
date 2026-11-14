# Serialized fail-closed admission lease

Historical #4580 recovery. This is a **local, single-host** admission component,
not a distributed GitHub rate limiter or a replacement for repository rules.

All cooperating writers must use the same SQLite database in a trusted local
directory. BEGIN IMMEDIATE serializes check-and-reserve operations. At most
four acquisitions per rolling 60 seconds are permitted, counting unfinished
reservations. A same-head active reservation cannot be duplicated, even by the
same lane. Tokens are random, bound to lane, actor, head and expiry, and can be
consumed only once. Clock regression, corruption and missing ledgers fail closed
for an existing instance. Each instance freezes its absolute path and pins the
observed file identity; missing, relinked or replaced ledgers are rejected.
Clock samples outside the supported civil-time range are rejected before any
arithmetic or SQL mutation. A new instance may bootstrap a deliberately new
database; the operator must provision and preserve its path. The path checks
are not descriptor-bound SQLite custody and do not protect against a malicious
same-UID writer, inode reuse, modification in place, or a false wall clock.
Use a trusted directory and an independently trusted host clock.

The historical JSON ledger is not silently migrated or reused. Existing JSON
files must be retained for audit and deliberately replaced by a new SQLite
ledger only after accounting for outstanding reservations. Do not use this
implementation on network filesystems or across independent runner hosts.

```python
from pathlib import Path
from skeleton.admission.lease import AdmissionLease

lease = AdmissionLease(Path("data/admission-ledger.sqlite3"))
token = lease.acquire("A", expected_sha=current_head, actor="studio")
if token is not None:
    # The remote transport MUST independently enforce exact-head compare-and-swap.
    # Consume locally before dispatch: no blind retry if dispatch fails.
    lease.release(token, actual_sha=current_head)
    # Dispatch only once using the original expected head as CAS precondition.
```

The local token admission limit is not a guarantee about the timing of remote
push completion. This module does not read GitHub refs or dispatch any writes.
The caller owns the remote CAS and must not reuse a consumed token.

Qualification: `python -m pytest -q skeleton/testing/test_admission_lease.py`.
Before enabling remote writes, require independent integration and exact-head
review; local tests do not prove global rate limit enforcement.
