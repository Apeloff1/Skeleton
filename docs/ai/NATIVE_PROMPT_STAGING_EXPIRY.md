# Native prompt staging lifetime and RAM custody

A staged plaintext prompt is an **ephemeral RAM grant**, not a durable
execution authorization. The registry now applies a bounded monotonic age
(5 minutes by default, configurable up to one hour) to every staged prompt.
Every stage, claim, revoke and status operation revalidates the clock and
expires stale grants under the same registry lock before making capacity
available. Expiry releases tenant/global staged RAM but burns the request ID
for the process lifetime; a stale worker cannot claim or replay it.

Clock regression, invalid samples, malformed staging timestamps and ledger
accounting mismatches fail closed. Forked processes cannot reuse inherited
locks or prompt grants. A claim before its deadline remains one-use; after
claim the durable execution journal still controls crash/retry semantics.
No plaintext, request ID or tenant identity is exposed in budget telemetry.
Unknown GPU/thermal/device telemetry is not made safe by local execution.

Focused tests: `pytest -q skeleton/testing/test_native_prompt_budget.py`
plus native fair-stream backend and execution journal tests. Exact-head
security/CI, hardware qualification and release holds remain required.
