# Competitive AI Benchmark Governance

Machine authority: `machine/competitive_ai_benchmark_governance.json`

This specification governs how Skeleton may claim that an engineering family is competitively superior. It exists because a 200-level engineering ladder is only meaningful when its final claims cannot be selected after seeing favorable results.

## Core rule

A competitive claim is **pre-registered before challenger results are visible**. The comparison freezes the baseline, workload, primary outcome, metric directions, minimum practical effects, protected non-inferiority margins, hard gates, model/provider settings, hardware/runtime environment, resource budget, exclusions, uncertainty method, multiplicity handling and stopping rule.

Material changes restart qualification. They do not become editorial adjustments to an already-running study.

## Promotion semantics

The promotion chain is:

`planned -> implemented -> hardened -> benchmark_preregistered -> evaluation_complete -> independently_verified -> superior`

A superior result becomes `stale` whenever any material bound identity or operating envelope changes. A stale claim returns to superior only after a new preregistration and full requalification. New contradictory evidence may demote the claim.

## Anti-gaming rules

Skeleton does not permit post-hoc primary metric changes, hidden failed slices, weaker replacement baselines, correlated metric counting, aggregate wins that hide critical-slice failures, median-only serving claims, generator-only grading, or deletion of negative findings.

The goal is not to maximize the number of claimed wins. The goal is to maximize the number of **reproducible, operationally safe, independently defensible wins**.

## Statistical decision rule

The primary outcome must satisfy its preregistered win or strict non-inferiority rule with the declared uncertainty method. At least three materially distinct dominance targets must satisfy their practical-effect thresholds. Non-compensable security, privacy, authority, tenancy, acknowledged-state, rollback and bounded-execution gates remain absolute.

If many metrics or workload slices could create a favorable conclusion, the study must define multiplicity control or a hierarchical decision procedure before results are visible.

## Cross-family golden journeys

Eight cross-family journeys prevent local benchmark wins from producing a globally brittle system:

- CFQ-01: reasoning + long context + retrieval truth.
- CFQ-02: memory + privacy + tenant lifecycle.
- CFQ-03: agent + tool + planning transaction.
- CFQ-04: coding + safety + independent verification.
- CFQ-05: multimodal + realtime untrusted input.
- CFQ-06: routing + serving + scale degradation.
- CFQ-07: learning + safety + rollback.
- CFQ-08: scientific verification + provenance.

Family-level superiority can therefore be challenged by cross-plane evidence when integration reveals a failure that an isolated benchmark hid.

## Evidence

A promotable result preserves preregistration, exact candidate and baseline identities, workload identity, raw results, environment, resource budget, exclusions, statistical report, hard-gate report, applicable cross-family journeys, independent verdict and claim-expiration triggers.

No marketing sentence, demo video, cherry-picked transcript, isolated benchmark number or model-authored self-evaluation substitutes for that evidence.

Validation:

```bash
python scripts/check_competitive_ai_benchmark_governance.py --json
python -m pytest -q --noconftest tests/test_competitive_ai_benchmark_governance.py
```
