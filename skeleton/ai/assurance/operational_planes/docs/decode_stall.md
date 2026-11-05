# runtime.decode_stall: operational admission guard

Detect stalled decoding

## Ownership

- Domain: `runtime`
- Policy identifier: `runtime.decode_stall`
- Python contract: `policies/decode_stall.py`
- JSON schema: `contracts/decode_stall.schema.json`
- Synthetic examples: `scenarios/decode_stall.json`
- Tests: `skeleton/testing/test_operational_plane_decode_stall.py`

## Required evidence

The external collector supplies two observed nonnegative finite measurements.
The primary signal is `decode_token_gap_ms` with an inclusive ceiling of **1200**.
The secondary signal is `decode_queue_depth` with an inclusive ceiling of **64**.
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
