# Long-context CPU capacity: claim-time disk revalidation

The cooperative CPU capacity guard rechecks the immutable checkpoint window,
trusted principal, live pressure latch, and a **fresh** descriptor-anchored spool
capacity observation before consuming a one-shot reservation. An observation is
not an allocation or execution lease. A capacity result must have the canonical
non-authorizing schema, exact request bytes, nonnegative integral counters,
consistent quota arithmetic, and an observed available state. Any malformed
or unavailable reading revokes that reservation without granting execution.

A fair-cycle reserve checks the aggregate requested bytes atomically within
the guard's process; individual claims each recheck their own request. A disk
that becomes full after reserve, or between two fair-cycle claims, can deny a
claim. No cross-process reservation, GPU qualification, or backend authority
is implied. Guarded publication must independently enforce its quota and
filesystem race fences under the spool's cross-process publication lock.

Regression coverage: disk pressure after reservation, disappearing disk
telemetry, inconsistent quota arithmetic, forged lease/qualification flags,
and two-stream partial claim-time revocation.
