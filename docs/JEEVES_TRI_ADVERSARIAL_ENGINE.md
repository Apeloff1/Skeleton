# Jeeves Tri-Engine Adversarial Quality Boundary

Jeeves uses a fail-closed release boundary for generated artifacts. The release path is now a **tri-engine** architecture: three independent lanes, each executing the complete 100-gate adversarial registry.

## Architecture

| Lane | Purpose | Gates |
| --- | --- | ---: |
| `quality` | Correctness, completeness, evidence, arithmetic, reproducibility, calibration, consistency | 100 |
| `adversarial_quality` | Hostile assumptions, false premises, framing, manipulation, perturbation, model fragility, negative paths | 100 |
| `integrity` | Tool provenance, failures, side effects, secrets, prompt injection, isolation, release integrity | 100 |

A normal release therefore produces **300 gate results**. No averaging can rescue a failed lane. The combined release is allowed only when all three underlying 100-gate engines independently issue their release seal.

## Thresholds and hard blockers

The default minimum is 95/100 for every lane. The underlying 100-level engine retains its critical hard blockers, including evidence attachment, unsupported claims, future-information leakage, arithmetic recomputation, forecast calibration, prediction/fact separation, tool-output validation, side-effect boundaries, secret detection, prompt-injection resistance, hallucination/consistency sweeps, confidence ceiling, independent final judge, and release seal.

Lane-specific thresholds can be supplied to `TriAdversarialEngine` without weakening another lane. A lane that blocks always blocks the combined release regardless of the other two scores.

## Batched adversarial judging

The optional semantic judge is batched. Each 100-gate lane uses at most ten category calls, so a full tri-engine pass uses at most thirty judge calls rather than 300 model calls. Deterministic local blockers always remain authoritative: a judge can make a result stricter, not downgrade a deterministic block.

Each judge receives:

- `tri_lane`: the active lane name.
- `tri_focus_gates`: the high-value gates for that lane.
- `tri_gate_count`: always `100`.

Different judges may be configured for `quality`, `adversarial_quality`, and `integrity`.

## Lane-specific attack signals

Global metadata is evaluated by all lanes. Lane-specific metadata is placed under `tri_lanes`:

```python
metadata = {
    "creation_type": "game_spec",
    "tri_lanes": {
        "quality": {
            "adverse_signals": {"arithmetic_error": True},
        },
        "adversarial_quality": {
            "adverse_signals": {"false_premise_injection_test": True},
        },
        "integrity": {
            "adverse_signals": {"side_effect_boundary": True},
        },
    },
}
```

Lane overlays are recursively merged with global metadata and do not leak into sibling lanes.

## Repair and release

Each lane may run bounded repair rounds. A repaired candidate flows into the next lane so later engines evaluate the latest artifact. A blocked lane does not short-circuit evaluation; the remaining lanes still run to produce complete diagnostics.

Successful releases contain:

- three independent 100-gate decisions,
- 300 flattened gate results,
- a normalized 0-100 score,
- a raw 0-300 score,
- individual lane seals,
- a final combined seal over the candidate and all lane seals.

The combined seal uses HMAC-SHA256 when `SKELETON_TRI_ADVERSARIAL_SEAL_KEY` is configured. It falls back to `SKELETON_ADVERSARIAL_SEAL_KEY`, then to an unsigned SHA-256 integrity digest when no key is configured.

## Enforced paths

The exported NPC, game-logic, and animation generators pass through `guard_tri_creation()` before returning. `GameForge` applies the same 3x100 boundary again to the final packaged `GameSpec`, preventing individually valid components from bypassing validation after final assembly.

The canonical `scripts/quality-gates.sh` suite includes both the atomic 100-gate engine regressions and the tri-engine regressions.
