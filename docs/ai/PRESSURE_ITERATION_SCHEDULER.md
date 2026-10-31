# Pressure-aware iteration token budgets

The existing deterministic prefill/decode `IterationScheduler` can now
compile `plan_pressure_aware` receipts from a caller-measured finite pressure
fraction. The effective token budget only tightens the operator's configured
ceiling and preserves decode prioritization and stable plan identity.
A distinct digest binds measured source, pressure, effective budget and the
underlying deterministic iteration plan.

Missing, nonfinite or malformed measurements are rejected. Source labels
are provenance supplied by the caller, not OS/device attestation. This is a
scheduling plan, not proof of kernel execution or GPU acceleration.
Input work counts and request identities are bounded before sorting.

Tests: `python -m pytest skeleton/testing/test_pressure_iteration_scheduler.py -q`.
