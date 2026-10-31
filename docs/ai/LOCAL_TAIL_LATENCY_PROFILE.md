# Local inference tail-latency qualification receipts

The canonical model runtime now has an opt-in, source-bound profiler at
skeleton/ai/model_runtime/tail_latency_profile.py. It consumes real
ExecutionTiming observations and the existing RequestTelemetry/ServingTelemetryWindow
contracts. It does not launch an inference provider or manufacture timing
observations. It can also evaluate explicitly simulated fixtures without
mistaking them for hardware evidence.

## Why the profiler exists

An average latency or goodput percentage hides tail starvation. Every accepted
performance claim needs p95/p99 latency and resource saturation under the
same model, tokenizer, workload, source, policy and hardware identity.
This profiler records exact per-request observations, computes deterministic
nearest-rank p50/p95/p99, canonical SLO compliance and serial token-throughput
accounting, and binds all reported values to an ordered SHA-256 digest.

An identity includes SHA-256 model, tokenizer, workload and policy digests,
the Git source commit SHA, a backend and device label, and explicit
measured/simulated evidence provenance. A comparison is refused when any
identity field differs. The source SHA may be a 40-hex Git SHA-1 or a 64-hex
SHA-256 object ID; it is not a model hash.

## Usage

The read-only command is available without a new provider or dependency:

~~~sh
python -m skeleton.ai.model_runtime.tail_latency_cli < profile.json
~~~

Input JSON schema: skeleton.ai.tail-profile-command.v1.

Required top-level fields: schema, identity, records, checkpoint, slo,
baseline, allowed_regression_ppm. The command consumes at most 512 KiB from
standard input and returns schema skeleton.ai.tail-profile-receipt.v1.
The CLI never accepts prompt text, weights, credentials or output tokens as
strings. It records only request IDs, timing counters, token counts and
resource measurements.

Each record has a timing object matching the canonical ExecutionTiming
constructor (request_id, started_ns, first_token_ns, completed_ns,
output_tokens, prompt_tokens, prefix_reused_tokens), and a resource object
with physical RAM, swap, CPU load in parts per million, optional complete GPU
free/total counters and a thermal status of unavailable, measured_ok or
measured_hold. Unknown GPU capacity must remain null rather than zero.

To continue a prior window, pass the returned checkpoint and append only new
request identities. The checkpoint includes a SHA-256 integrity digest, not
authentication; external storage must provide authorization and atomicity.

## Qualification semantics

The profiler requires at least 100 observations to label a measured tail
profile. Fewer observations remain insufficient_samples; simulated data
remains simulated. A missing thermal trip signal or measured thermal hold is
explicitly reported. The profile does not assert that the device, workload,
model quality, provider or installer is certified.

Comparison only accepts two profiles with identical model, tokenizer,
workload, source, policy, backend and device identity, both measured and
sufficiently sampled, and valid digest receipts. It compares p95 and p99
for time-to-first-token, inter-token time and end-to-end latency. The
allowed regression threshold is an explicit integer in parts per million.
An unknown/insufficient profile yields pending, not success.

The reported serial_tokens_per_second_milli divides total output tokens
by the sum of per-request execution durations. It is not wall-clock
multistream throughput. For concurrent throughput claims, record wall-clock
workload duration separately with a trustworthy owner.

## Security and limitations

The profile is metadata only; request IDs should be opaque and must not
contain user prompts or private paths. All counters are bounded integers.
No implicit eviction occurs, and duplicates fail closed. Integrity digests
detect accidental modification but do not authenticate an adversarial
publisher. Operator-supplied evidence provenance is not independently
attested; a trusted measurement capture path is required before external
release or device claims.

Run the focused source-backed tests after construction:

~~~sh
python -m pytest -q skeleton/testing/test_tail_latency_profile.py
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
python scripts/check_provider_bootstrap.py
~~~

The deterministic tests include exact percentile boundaries, 100-sample
qualification, simulated/thermal holds, identity mismatches, regression
detection, replay, tamper, resource consistency and bounded CLI parsing.
Real device qualification still requires direct on-target macOS Metal,
Windows WDDM and Linux CUDA/ROCm runs with actual model weights, failure
injection, power/thermal observations and p95/p99 saturation curves.
