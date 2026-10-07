#!/usr/bin/env python3
"""Compare full-depth and mixture-of-depths inference on the owned transformer."""
from __future__ import annotations

import argparse
import json
import statistics
import time

from skeleton.cortex.mixture_depth import MixtureOfDepths
from skeleton.cortex.transformer import TinyTransformer


def _elapsed(fn, repeats: int) -> tuple[float, float]:
    samples = []
    for _ in range(max(1, repeats)):
        started = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - started)
    return statistics.mean(samples), statistics.median(samples)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layers", type=int, default=6)
    parser.add_argument("--dim", type=int, default=32)
    parser.add_argument("--ctx", type=int, default=16)
    parser.add_argument("--d-ff", type=int, default=64)
    parser.add_argument("--threshold", type=float, default=0.02)
    parser.add_argument("--min-depth", type=int, default=2)
    parser.add_argument("--repeats", type=int, default=40)
    args = parser.parse_args()

    vocab = tuple(f"tok-{i}" for i in range(max(32, args.ctx * 2)))
    model = TinyTransformer(
        vocab=vocab,
        dim=args.dim,
        ctx=args.ctx,
        seed=23,
        n_heads=4,
        n_layers=args.layers,
        d_ff=args.d_ff,
    )
    ids = [model._id(vocab[i % len(vocab)]) for i in range(args.ctx)]
    full = MixtureOfDepths(model, enabled=False)
    adaptive = MixtureOfDepths(
        model,
        threshold=args.threshold,
        min_depth=args.min_depth,
    )

    # Warm both paths so import/setup noise does not dominate tiny models.
    full.logits_ids(ids)
    adaptive.logits_ids(ids)
    full_mean, full_median = _elapsed(lambda: full.logits_ids(ids), args.repeats)
    adaptive_mean, adaptive_median = _elapsed(
        lambda: adaptive.logits_ids(ids), args.repeats
    )

    result = {
        "config": {
            "layers": model.n_layers,
            "dim": model.dim,
            "ctx": model.ctx,
            "d_ff": model.d_ff,
            "threshold": args.threshold,
            "min_depth": args.min_depth,
            "repeats": args.repeats,
        },
        "full_depth": {
            "mean_seconds": full_mean,
            "median_seconds": full_median,
        },
        "adaptive": {
            "mean_seconds": adaptive_mean,
            "median_seconds": adaptive_median,
            "metrics": adaptive.metrics(),
        },
        "wall_clock_speedup": full_mean / adaptive_mean if adaptive_mean else None,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
