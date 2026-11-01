# Long-context telemetry fusion — observational only

The offline runtime exposes `LongContextTelemetryFusion` through the
model-runtime lazy export map and `long_context_cli head-observe-fused`.
It samples host PSI, cgroup-v2 pressure, and monotonic cgroup event deltas
without reading model prompts, writing spool state, or authorizing inference.

**State machine:** `baseline_required` after a first valid event sample,
`observed` only after a validated event delta and both validated pressure
sources, and `unavailable` on missing, forged, nonmonotonic or slow
observations. Every state is non-authorizing. Sampling is sequential, not
atomic, and process-local; a forked child must construct a fresh monitor.

**Conservative precedence:** unknown beats critical, elevated and normal.
Critical beats elevated, elevated beats normal. Any unavailable source
keeps its signals unknown. OOM and CPU throttle event deltas can only
increase severity, never clear unknown evidence. Thermal and energy
remain unknown unless independently qualified future source adapters
are implemented; this release has none.

**Security:** strict schema, integer and reason validation; bounded
observation duration; monotonic clock check; fork-safe lock ownership;
no device qualification, no execution lease, no admission grant, no
cross-source snapshot attestation. The SHA-256 digest is an unkeyed
correlation identifier, not an authenticity proof.

The CLI returns a payload-free JSON observation. Backend inference
must separately validate authorization, memory/disk capacity, KV,
tokenizer identity, model provenance, thermal/energy state and live
hardware limits before any actual work. Do not use diagnostic normal
readings to bypass a required safety gate.
