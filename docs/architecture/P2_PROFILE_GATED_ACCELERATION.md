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
