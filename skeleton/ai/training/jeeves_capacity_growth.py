"""Function-preserving growth of the real serving-derived Jeeves Torch candidate.

This grows actual *trainable feed-forward weights*, not metadata or synthetic
parameter totals. Existing tensor rows are copied verbatim, new hidden neurons
are initialized deterministically, and new output columns start at zero.
That preserves the old model function to float32 tolerance before real SGD
teaches the new neurons. Only the *candidate clone* is modified.

Neural width/depth/attention-head growth is intentionally NOT faked. Existing
live native checkpoints and unsupported architectures fail closed.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
from typing import Any

PROFILE_FACTORS = {
    "none": (1, 1),
    "micro": (9, 8),
    "balanced": (5, 4),
    "large": (3, 2),
    "xlarge": (2, 1),
}
MAX_FFN = 16384
MAX_ADDED = 2000000
MAX_TOTAL = 16000000


class CapacityGrowthError(ValueError):
    """Invalid architecture, non-preserving expansion or resource admission."""


def parameter_count(model: Any) -> int:
    """Count actual trainable tensors owned by the model."""
    net = getattr(model, "net", None)
    if net is None or not hasattr(net, "parameters"):
        raise CapacityGrowthError("requires real PyTorch tensor-backed candidate")
    return sum(int(p.numel()) for p in net.parameters() if p.requires_grad)


def growth_plan(model: Any, profile: str) -> dict[str, Any]:
    if profile not in PROFILE_FACTORS:
        raise CapacityGrowthError("unsupported FFN growth profile")
    from skeleton.cortex.torch_lm import TorchTransformer
    if not isinstance(model, TorchTransformer):
        raise CapacityGrowthError("feed-forward growth requires a real torch-stack Jeeves snapshot")
    factor_n, factor_d = PROFILE_FACTORS[profile]
    before_ffn = int(model.d_ff)
    before = parameter_count(model)
    # Rounding to the next integer preserves monotonic growth for small LMs.
    after_ffn = max(before_ffn + (1 if profile != "none" else 0),
                    (before_ffn * factor_n + factor_d - 1) // factor_d)
    if profile == "none":
        after_ffn = before_ffn
    added = (after_ffn - before_ffn) * (2 * int(model.dim) + 1) * int(model.n_layers)
    if (after_ffn > MAX_FFN or added > MAX_ADDED or before + added > MAX_TOTAL
            or before + added >= 2**31):
        raise CapacityGrowthError("FFN growth exceeds independent parameter/resource limits")
    return {
        "profile": profile,
        "architecture": "JeevesCortex.torch-stack",
        "old_ffn_width": before_ffn,
        "new_ffn_width": after_ffn,
        "new_neurons_per_layer": after_ffn - before_ffn,
        "transformer_layers": int(model.n_layers),
        "existing_trainable_parameters": before,
        "new_trainable_parameters": added,
        "projected_trainable_parameters": before + added,
        "source_token_count": len(model.itos),
        "source_training_steps": model.steps,
        "source_fitted_documents": model.fitted,
        "growth_is_never_independent_capability_proof": True,
    }


def grow_feedforward(model: Any, *, profile: str,
                     max_added_parameters: int = 500000,
                     expected_snapshot_sha256: str | None = None) -> tuple[Any, dict]:
    """Return strictly equivalent larger *candidate* Torch model.

    Growth does not itself train or improve model outputs; newly reachable FFN
    weights become optimizable on subsequent verified training steps.
    """
    if type(max_added_parameters) is not int or not 1 <= max_added_parameters <= MAX_ADDED:
        raise CapacityGrowthError("explicit new-parameter admission must be in range 1..2,000,000")
    plan = growth_plan(model, profile)
    if plan["new_trainable_parameters"] > max_added_parameters:
        raise CapacityGrowthError("candidate parameter increase exceeds operator budget")
    original = model.snapshot()
    encoded = json.dumps(original, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    original_sha = sha256(encoded).hexdigest()
    if expected_snapshot_sha256 is not None and original_sha != expected_snapshot_sha256:
        raise CapacityGrowthError("checkpoint expansion input hash differs from verified source")
    if profile == "none":
        return model, {**plan, "input_snapshot_sha256": original_sha,
                       "trainable_parameter_count_verified": True,
                       "logit_equivalence_max_abs_diff": 0.0,
                       "weights_trained_by_growth": False}
    torch = model.torch
    # Reserve a bounded memory cushion before reconstructing a full second net.
    # Memory admission is intentionally stronger than tensor size alone.
    from .jeeves_parallel_mirrors import available_memory_bytes
    required = max(256 * 1024**2, 24 * (plan["projected_trainable_parameters"]))
    if available_memory_bytes() < required:
        raise CapacityGrowthError("not enough host RAM for two temporary model copies")
    previous_state = original.get("state")
    if not isinstance(previous_state, dict):
        raise CapacityGrowthError("Torch snapshot lacks actual tensor state")
    state = dict(previous_state)
    delta = plan["new_neurons_per_layer"]
    D = int(model.dim)
    old = plan["old_ffn_width"]
    for index in range(int(model.n_layers)):
        prefix = f"enc.layers.{index}."
        a = prefix + "linear1.weight"
        b = prefix + "linear1.bias"
        c = prefix + "linear2.weight"
        if not all(key in previous_state for key in (a, b, c)):
            raise CapacityGrowthError("unsupported Torch FFN tensor layout")
        w1 = torch.tensor(previous_state[a], dtype=torch.float32, device="cpu")
        bias = torch.tensor(previous_state[b], dtype=torch.float32, device="cpu")
        w2 = torch.tensor(previous_state[c], dtype=torch.float32, device="cpu")
        if tuple(w1.shape) != (old, D) or tuple(bias.shape) != (old,) or tuple(w2.shape) != (D, old):
            raise CapacityGrowthError("serving FFN tensor dimensions do not match checkpoint claims")
        # A local generator avoids mutating process-global RNG or production model.
        seed = int(sha256((original_sha + ":" + str(index)).encode()).hexdigest()[:16], 16)
        gen = torch.Generator(device="cpu").manual_seed(seed)
        new_rows = torch.randn((delta, D), generator=gen, dtype=torch.float32) * (
            1.0 / math.sqrt(D))
        state[a] = torch.cat([w1, new_rows], dim=0).tolist()
        state[b] = torch.cat([bias, torch.zeros(delta)], dim=0).tolist()
        # No new contribution until trained; gradients reach new output columns
        # on the first SGD step because their hidden activations are nonzero.
        state[c] = torch.cat([w2, torch.zeros(D, delta)], dim=1).tolist()
    widened_snapshot = {**original, "d_ff": plan["new_ffn_width"], "state": state}
    from skeleton.cortex.torch_lm import TorchTransformer
    larger = TorchTransformer.from_snapshot(widened_snapshot)
    if larger.itos != model.itos or larger.steps != model.steps or larger.fitted != model.fitted:
        raise CapacityGrowthError("vocabulary IDs or training lineage mutated during growth")
    counted = parameter_count(larger)
    if counted != plan["projected_trainable_parameters"]:
        raise CapacityGrowthError("claimed additional parameters differ from actual trainable tensors")
    # Probe diverse source-known token prefixes; output should remain equivalent.
    # Avoid held-out data: equivalence concerns architecture only.
    samples = [[min(i, len(model.itos) - 1)] for i in range(min(8, len(model.itos)))]
    if len(model.itos) > 2:
        samples.append([1, 2])
    tolerance = 2.0e-5
    maximum = 0.0
    model.net.eval()
    larger.net.eval()
    with torch.no_grad():
        for ids in samples:
            left = model.net(torch.tensor([ids], dtype=torch.long, device=model.device_obj))
            right = larger.net(torch.tensor([ids], dtype=torch.long, device=larger.device_obj))
            diff = float(torch.max(torch.abs(left.float().cpu() - right.float().cpu())))
            if not math.isfinite(diff) or diff > tolerance:
                raise CapacityGrowthError("new tensor rows changed the parent model before SGD")
            maximum = max(maximum, diff)
    if larger.snapshot()["state"] != state:
        raise CapacityGrowthError("grown model failed exact tensor serialization roundtrip")
    return larger, {
        **plan, "input_snapshot_sha256": original_sha,
        "trainable_parameter_count_verified": True,
        "logit_equivalence_max_abs_diff": maximum,
        "logit_equivalence_tolerance": tolerance,
        "weights_trained_by_growth": False,
        "growth_candidate_only": True,
    }


def main(argv: list[str] | None = None) -> int:
    """Inspect actual live Torch FFN growth opportunities without making weights."""
    import argparse
    from pathlib import Path
    import sys
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True,
                        help="operator-pinned SKELETON_OWN checkpoint, never a demo model")
    parser.add_argument("--expected-sha256", required=True,
                        help="independently confirmed SHA of active checkpoint")
    parser.add_argument("--max-added-parameters", type=int, default=500000)
    parser.add_argument("--profile", choices=tuple(PROFILE_FACTORS),
                        help="report one growth profile, or all profiles")
    args = parser.parse_args(argv)
    try:
        from .jeeves_production_game_train import (
            _production_source, _active_snapshot, ProductionCheckpointError,
        )
        _path, blob, digest = _production_source(args.checkpoint, args.expected_sha256)
        selected, snapshot, mouth = _active_snapshot(blob)
        if snapshot.get("kind") != "torch-stack":
            raise CapacityGrowthError(
                "active production speaking weights are not Torch-stack; cannot widen safely")
        from skeleton.cortex.torch_lm import TorchTransformer
        model = TorchTransformer.from_snapshot(snapshot)
        requested = (args.profile,) if args.profile else tuple(PROFILE_FACTORS)
        options = []
        for profile in requested:
            try:
                plan = growth_plan(model, profile)
                plan["within_operator_budget"] = (
                    plan["new_trainable_parameters"] <= args.max_added_parameters)
                options.append(plan)
            except CapacityGrowthError as exc:
                options.append({"profile": profile, "status": "not_admitted",
                                "reason": str(exc)[:200]})
        result = {
            "schema_version": "skeleton.jeeves.capacity_plan.v1",
            "source_checkpoint_sha256": digest,
            "selected_speaking_model": selected, "speaking_mouth": mouth,
            "source_trainable_parameters": parameter_count(model),
            "planned_profiles": options,
            "actual_parameter_growth_executed": False,
            "optimizer_steps_executed": 0,
            "production_weights_modified": False,
            "candidate_promoted": False,
        }
        print(json.dumps(result, sort_keys=True))
        return 0
    except (CapacityGrowthError, ProductionCheckpointError,
            ValueError, OSError, RuntimeError, TypeError) as exc:
        print(json.dumps({"status": "blocked",
                          "reason": str(exc)[:350],
                          "production_weights_modified": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["CapacityGrowthError", "PROFILE_FACTORS", "growth_plan",
           "parameter_count", "grow_feedforward", "main"]
