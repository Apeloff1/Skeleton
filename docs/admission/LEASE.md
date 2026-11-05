# Serialized Fail-Closed Admission Lease

Addresses #4580.

Guarantees fewer than 5 admitted pushes per rolling 60 seconds via expected-SHA CAS lease.
Fail-closed on unavailable ledger, concurrent mutation, or SHA mismatch.

Usage:
```python
from skeleton.admission.lease import AdmissionLease
lease = AdmissionLease(Path("data/admission-ledger.json"))
token = lease.acquire(lane="A", expected_sha=current_head, actor="studio")
if token:
    # perform push
    lease.release(token, actual_sha=new_head)
```

Tests cover headroom exhaustion, concurrent same-SHA races, and release integrity.
No rate limit weakening. Exact-head review required before enabling remote writes.
