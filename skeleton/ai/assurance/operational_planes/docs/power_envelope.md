# hardware.power_envelope: operational admission guard

Bound device power

## Ownership

- Domain: `hardware`
- Policy identifier: `hardware.power_envelope`
- Python contract: `policies/power_envelope.py`
- JSON schema: `contracts/power_envelope.schema.json`
- Synthetic examples: `scenarios/power_envelope.json`
- Tests: `skeleton/testing/test_operational_plane_power_envelope.py`

## Required evidence

The external collector supplies two observed nonnegative finite measurements.
The primary signal is `device_power_watts` with an inclusive ceiling of **240**.
The secondary signal is `power_limit_events_per_min` with an inclusive ceiling of **3**.
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
