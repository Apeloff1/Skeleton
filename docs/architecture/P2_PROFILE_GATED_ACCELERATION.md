# P2 Profile-Gated Acceleration

This lane is stacked on the P2 quality/final-assembly lane and implements the explicit masterplan gaps in **VOL-032 High-Performance Native Core** and **VOL-033 Java / JVM Plane**.

Machine authority: `machine/acceleration_policy.json`

## Selection rule

Accelerator existence is not selection evidence. The reference implementation remains the default route until profile evidence is:

- bound to the exact candidate source identity;
- correct within the declared numerical tolerance;
- reproducible across the minimum run/environment requirements;
- faster than the non-compensable speedup threshold;
- crash- and timeout-free within the policy budget;
- backed by an available reference/fallback;
- isolated according to crash risk;
- protocol-compatible.

A very large speedup cannot compensate for correctness, crash, isolation or protocol failure.

## Isolation

Medium/high crash-risk candidates require a bounded subprocess boundary for automatic selection. Requests are JSON-bounded, time-bounded, run with an environment allowlist, and fail back to the reference path at the selection/control layer.

## JVM protocol

JVM candidates use `skeleton.acceleration.rpc@1.0` with explicit version negotiation, request identity, operation and deadline. Unknown versions reject rather than being interpreted optimistically.

All current candidates remain `candidate_unpromoted`; this lane does not claim benchmark superiority, maturity promotion, or P2-NATIVE-01 completion.


## Profiling receipts

`skeleton/native/profiling.py` produces paired reference/candidate evidence rather than accepting hand-authored speed claims. Each run binds the receipt to the candidate source identity and a deterministic, non-secret environment fingerprint; interleaves reference and candidate calls to reduce temporal skew; records medians, correctness, maximum absolute error, crashes and timeouts; and refuses to mint a receipt if the candidate produces zero successful samples.

The profiler itself never promotes or routes traffic. Its output is input to the separate fail-closed selection engine.


## Canonical benchmark commands

Each machine-policy candidate declares one canonical `profile_command` and the exact source files used to derive its composite source identity. The runner currently covers native vector, JVM vector, JVM physics broad-phase, and JVM observability workloads.

The runner exits non-zero when the native compiler/library or Java runtime is unavailable, when the accelerator crashes/times out without any successful sample, or when its reference comparison cannot produce valid evidence. Missing prerequisites therefore cannot be recorded as a passing benchmark.


## Receipt ingestion and activation

`scripts/record_p2_acceleration_profile.py` is the only supported machine-policy ingestion path. It revalidates the receipt schema and current composite source identity, rejects duplicate receipt IDs, recomputes every non-compensable selection gate, and stores the derived decision.

A candidate with enough passing evidence becomes `evidence_qualified_unpromoted` by default while `automatic_selection` remains false. Activation is a separate explicit `--activate` operation and is rejected unless the complete evidence set qualifies. Even an activated candidate remains *unpromoted* at the masterplan maturity/signature layer.
