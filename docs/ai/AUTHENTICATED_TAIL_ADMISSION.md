# Authenticated p99-driven local admission

The canonical tail profiler produces a **digest**, not a signature.
A profile JSON claiming `evidence=measured` is attacker-editable and cannot
on its own authorize new CPU worker slots. The tail admission governor now
holds new admission at zero without an HMAC attestation from the trusted local
measurement owner. The attestation binds the profile digest, exact session,
policy, generation and fresh RAM observation.

Only a trusted app execution component holding an independent 32+ byte
attestation key may call `sign_tail_observation`, and only after the canonical
profiler has collected actual local OS observations. Never expose the key to
the CLI, untrusted JSON, logs, telemetry payloads, or the model itself.
Use `observe(..., attestation=..., attestation_key=..., session_id=...)` and
persist the returned governor checkpoint under an external generation CAS
before dispatch. Wrong-key, wrong-session, stale-generation and changed-RAM
proofs reject before mutation; missing proof holds capacity at zero.

An authenticated local measurement is still **not** device qualification.
An HMAC does not prove a sensor's provenance, model correctness, GPU
reservation, thermal stability or a consumer-device performance target.
Continue using canonical hardware probes, conservative unknown handling,
actual backend enforcement, and platform-specific qualification tests.
