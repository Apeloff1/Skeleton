"""Offline reproducible performance probe for Skeleton's owned transformer.

This measures an *untrained, deterministic* transformer execution graph. It
does not measure language quality or imply frontier-model capabilities. No
network, model download, secrets or hosted provider is involved.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from typing import Sequence

from skeleton.cortex.transformer import KVCache, TinyTransformer


def percentile(samples: Sequence[float], fraction: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))]


def synchronize(device: str) -> None:
    if device not in {"cuda", "mps"}:
        return
    import torch
    if device == "cuda":
        torch.cuda.synchronize()
    else:
        torch.mps.synchronize()


def benchmark(args: argparse.Namespace) -> dict[str, object]:
    for name in ("dim", "context", "heads", "layers", "prefill", "decode", "runs"):
        value = getattr(args, name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    if args.warmup < 0 or args.dim % args.heads:
        raise ValueError("invalid warmup or non-divisible attention dimensions")
    if args.context < 2 or args.prefill + args.decode > args.context:
        raise ValueError("prefill + decode must fit within the selected context")
    if args.dim > 512 or args.layers > 12 or args.context > 2048:
        raise ValueError("benchmark size must remain consumer-hardware bounded")
    if args.ffn < 0 or args.ffn > 2048:
        raise ValueError("invalid feed-forward width")

    model = TinyTransformer(
        vocab=tuple(f"t{i}" for i in range(32)),
        dim=args.dim, ctx=args.context, n_heads=args.heads,
        n_layers=args.layers, d_ff=args.ffn, norm="rms",
        ffn_kind="swiglu", position_mode=args.position_mode,
        seed=17,
    )
    prompt = tuple((i % (model.V - 1)) + 1 for i in range(args.prefill))
    reference = TinyTransformer.from_snapshot(model.snapshot())
    expected = reference._logits(prompt)
    kv_dtype = getattr(args, "kv_dtype", "fp32")
    prefill_query_chunk = getattr(args, "prefill_query_chunk", None)
    if prefill_query_chunk is not None and (
        prefill_query_chunk < 1 or prefill_query_chunk > args.context
    ):
        raise ValueError("prefill_query_chunk must fit selected context")
    kv_limit_mib = getattr(args, "kv_limit_mib", None)
    if kv_limit_mib is not None and kv_limit_mib < 1:
        raise ValueError("kv_limit_mib must be a positive integer")
    if args.device == "cpu" and (
        kv_dtype != "fp32" or kv_limit_mib is not None
        or prefill_query_chunk is not None
    ):
        raise ValueError("KV precision and allocation caps require a Torch accelerator")
    model.to(
        args.device,
        kv_dtype=kv_dtype,
        max_kv_bytes=kv_limit_mib * (1024 ** 2) if kv_limit_mib else None,
        prefill_query_chunk=prefill_query_chunk,
    )
    expected_accel = {
        "cuda": "cuda",
        "gpu": "cuda",
        "mps": "mps",
        "torch": "cpu",
        "torch-cpu": "cpu",
    }.get(args.device)
    if expected_accel is not None and (
        model.device != expected_accel or not model.resident
    ):
        raise RuntimeError(
            f"device {args.device} unavailable; refusing to benchmark fallback as requested hardware"
        )

    if (
        kv_dtype != "fp32" or kv_limit_mib is not None
        or prefill_query_chunk is not None
    ) and model._accel is None:
        raise RuntimeError("requested Torch KV precision/budget unavailable on selected device")

    prefill_ms: list[float] = []
    decode_ms: list[float] = []
    parity_error = 0.0

    for run in range(args.warmup + args.runs):
        cache = KVCache(model.n_layers, model.ctx)
        synchronize(model.device)
        start = time.perf_counter()
        logits = model._logits_window(prompt, cache)
        synchronize(model.device)
        first_ms = (time.perf_counter() - start) * 1000.0

        if run == args.warmup:
            parity_error = max(abs(a - b) for a, b in zip(logits, expected))
            if args.assert_parity and any(
                not math.isclose(
                    a, b,
                    rel_tol=3e-3 if kv_dtype == "bf16" else 1e-3 if kv_dtype == "fp16" else 2e-4,
                    abs_tol=3e-3 if kv_dtype == "bf16" else 1e-3 if kv_dtype == "fp16" else 2e-4,
                )
                for a, b in zip(logits, expected)
            ):
                raise RuntimeError("accelerator and reference next-token logits diverged")

        output = list(prompt)
        iteration_ms: list[float] = []
        for _ in range(args.decode):
            next_token = max(range(len(logits)), key=logits.__getitem__)
            output.append(next_token)
            synchronize(model.device)
            started = time.perf_counter()
            logits = model._logits_window(output, cache)
            synchronize(model.device)
            iteration_ms.append((time.perf_counter() - started) * 1000.0)

        if run >= args.warmup:
            prefill_ms.append(first_ms)
            decode_ms.extend(iteration_ms)

    total_decode_seconds = sum(decode_ms) / 1000.0
    sample = {
        "schema": "skeleton.consumer-transformer-benchmark.v1",
        "device_requested": args.device,
        "device_actual": model.device,
        "resident": model.resident,
        "kv_dtype": kv_dtype,
        "kv_limit_mib": kv_limit_mib,
        "prefill_query_chunk": prefill_query_chunk,
        "architecture": {
            "dim": model.dim, "heads": model.n_heads,
            "layers": model.n_layers, "context": model.ctx,
            "ffn": model.d_ff, "position_mode": model.position_mode,
        },
        "measured": {
            "runs": args.runs,
            "prompt_tokens": len(prompt),
            "decode_tokens_per_run": args.decode,
            "prefill_median_ms": round(statistics.median(prefill_ms), 5),
            "decode_p50_ms": round(percentile(decode_ms, 0.50), 5),
            "decode_p95_ms": round(percentile(decode_ms, 0.95), 5),
            "decode_tokens_per_second": round(
                (len(decode_ms) / total_decode_seconds), 5
            ) if total_decode_seconds else 0.0,
            "max_absolute_reference_logit_error": round(parity_error, 10),
        },
        "notes": "Untrained miniature model; performance only, not model quality",
    }
    if model._accel is not None:
        sample["measured"]["kv_reserved_bytes"] = int(model._accel.kv_reserved_bytes)
    if model.device == "cuda":
        import torch
        sample["measured"]["cuda_peak_allocated_bytes"] = int(
            torch.cuda.max_memory_allocated()
        )
    return sample


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", choices=(
        "auto", "cpu", "torch", "torch-cpu", "cuda", "gpu", "mps"
    ), default="auto")
    parser.add_argument("--dim", type=int, default=32)
    parser.add_argument("--heads", type=int, default=4)
    parser.add_argument("--layers", type=int, default=2)
    parser.add_argument("--context", type=int, default=128)
    parser.add_argument("--ffn", type=int, default=64)
    parser.add_argument("--prefill", type=int, default=32)
    parser.add_argument("--decode", type=int, default=8)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--position-mode", choices=("learned_rope", "rope"),
                        default="rope")
    parser.add_argument("--kv-dtype", choices=("fp32", "fp16", "bf16"),
                        default="fp32")
    parser.add_argument("--prefill-query-chunk", type=int, default=None,
                        help="opt-in bounded SDPA query tiles for long prompts")
    parser.add_argument("--kv-limit-mib", type=int, default=None,
                        help="hard Torch KV allocation ceiling in mebibytes")
    parser.add_argument("--assert-parity", action="store_true")
    args = parser.parse_args()
    print(json.dumps(benchmark(args), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
