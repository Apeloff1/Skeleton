# observability.cost_accounting: operational admission guard

Guard resource accounting

## Ownership

- Domain: `observability`
- Policy identifier: `observability.cost_accounting`
- Python contract: `policies/cost_accounting.py`
- JSON schema: `contracts/cost_accounting.schema.json`
- Synthetic examples: `scenarios/cost_accounting.json`
- Tests: `skeleton/testing/test_operational_plane_cost_accounting.py`

## Required evidence

The external collector supplies two observed nonnegative finite measurements.
The primary signal is `unbilled_compute_units` with an inclusive ceiling of **0**.
The secondary signal is `unreconciled_reservations` with an inclusive ceiling of **0**.
Both are required even when one appears to be within its safe range.

## Admission boundary

- Missing values, booleans, non-finite values and negative values block admission.
- Any reading exceeding its individual inclusive ceiling blocks admission.
- Snapshots older than 60 seconds or timestamped in the future block admission.
- A missing required signal is not replaced by a default or unrelated telemetry.
- A nominal result is a point-in-time measurement, not perpetual authorization.
- Decision is deterministic; the collector and decision caller own the clock.

## Operational response

On a blocked decision, stop new admissions for the affected scope.
Preserve the original measurement values in the authorized telemetry store.
Identify the offending signal and correct the underlying root cause.
Reobserve both signals with an independently established timestamp.
Reassess before resuming; never override a failed security or integrity gate.

## Limits and nonclaims

These defaults are conservative initial guardrails, not device calibration.
Unit semantics are encoded in the signal names; no silent unit conversion occurs.
The engine performs no I/O and grants no GitHub, tool or deployment permissions.
Thresholds require independent validation before production activation.
The included fixtures are synthetic and do not constitute device qualification.
