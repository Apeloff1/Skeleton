# P2 Quality and Final Assembly

Machine authority: `machine/p2_quality_control.json`

This lane implements the masterplan obligations in VOL-070, VOL-081, VOL-117, and VOL-120 without creating an alternate maturity or release authority.

## Quality vector

The quality vector is derived from the 15 engineering dimensions already present in `machine/ai_engineering_pass.json`. Every dimension is non-compensable. There is no weighted or averaged overall score that can hide a failed correctness, safety, recovery, NFR, compatibility, ownership, testing, or other required dimension.

A dimension passes only with evidence. Missing or failed required dimensions block qualification.

## Formal methods

P2 initially targets the two canonical finite-state lifecycle machines:

- operation lifecycle in `skeleton/contracts/operation.py`;
- AI execution lifecycle in `skeleton/contracts/ai_execution.py`.

The formal checker exhaustively verifies transition-domain completeness, declared targets, terminal absorption, reachability from the initial state, and terminal reachability from every state. Each result is bound to the source SHA-256. A proof is scoped to that source/model and is not a universal correctness claim.

## Project metrics

The registry separates activity, throughput, quality, risk, and outcome metrics. Ratios expose numerator and denominator, and all observations identify their canonical sources. Metrics have **zero completion or maturity authority**.

## Final assembly

The final-assembly harness runs a release-like exact-head gate set on Ubuntu 24.04 / Python 3.11.16 / x86_64 and binds gate output identities into one canonical SHA-256 evidence digest.

The structural CI run intentionally remains **not promotion-ready** because it does not fabricate independent verification and it carries unresolved masterplan risks as blocking dispositions. Promotion requires the presented evidence digest to exactly match independently verified evidence and every unresolved risk to have an authorized disposition.

This lane does not mark P2-QUAL-01 complete, sign any masterplan volume, or convert passing structural checks into maturity.
