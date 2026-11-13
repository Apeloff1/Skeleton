# agents.tool_loop: operational admission guard

Prevent repeated tool loops

## Ownership

- Domain: `agents`
- Policy identifier: `agents.tool_loop`
- Python contract: `policies/tool_loop.py`
- JSON schema: `contracts/tool_loop.schema.json`
- Synthetic examples: `scenarios/tool_loop.json`
- Tests: `skeleton/testing/test_operational_plane_tool_loop.py`

## Required evidence

The external collector supplies two observed nonnegative finite measurements.
The primary signal is `tool_calls_per_task` with an inclusive ceiling of **120**.
The secondary signal is `repeated_identical_actions` with an inclusive ceiling of **8**.
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
