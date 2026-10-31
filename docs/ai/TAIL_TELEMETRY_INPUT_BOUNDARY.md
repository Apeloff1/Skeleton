# Strict local inference telemetry input

The canonical offline tail-latency CLI now parses bounded UTF-8 JSON with
duplicate-key rejection, nonfinite number rejection, and iterative depth/node
budgets. A duplicate schema key cannot silently overwrite the intended
profile. JSON structure validation occurs before the canonical profile is
modified. Invalid input returns a nonzero exit code without model execution.

The CLI explicitly labels all operator-supplied JSON as **unverified** and
never asserts hardware or admission qualification, even when a user-supplied
identity contains `evidence: measured`. The independent signed
TailAdmissionGovernor contract remains necessary for live worker admission.
No GPU/Metal, consumer-device or throughput qualification is inferred.
