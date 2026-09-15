# Mixture of Depths (F-6)

`MixtureOfDepths` adds opt-in dynamic token depth to Skeleton's owned pure-Python `TinyTransformer` without changing training, snapshots, or the transformer's default full-depth behavior.

## Routing contract

The controller measures the root-mean-square residual change after each transformer block. Once a token has executed `min_depth` blocks and its residual RMS is less than or equal to the configured threshold for that layer, the token exits. Its residual state is then frozen for the rest of the forward pass.

Frozen tokens are **not removed from causal context**. Later active tokens can still read them through key/value projections, while query projection, attention-query work, output projection, residual update, and FFN work are skipped for the exited token. This is intentionally different from compacting the sequence, which would shift RoPE positions and change the attention context.

The output remains a fixed `tokens × hidden_dim` matrix. The controller is inference-only; `TinyTransformer.fit()` and `_sgd()` continue to use the original full-depth path.

## Threshold schedules

A scalar threshold is held across every layer:

```python
from skeleton.cortex.mixture_depth import MixtureOfDepths

router = MixtureOfDepths(model, threshold=0.015, min_depth=2)
logits = router.logits_ids(ids)
print(router.metrics())
```

A sequence supplies a per-layer schedule. If the schedule is shorter than the model depth, its final value is held for all remaining layers:

```python
router = MixtureOfDepths(
    model,
    threshold=(0.005, 0.01, 0.02, 0.03),
    min_depth=2,
)
```

`float("inf")` forces eligible tokens to exit; a negative threshold forces full depth and is useful for calibration or A/B checks.

## Telemetry

Every routed forward exposes:

- `token_depths`
- `mean_depth`
- p50 / p90 / p95 effective depth
- active and full token/block update counts
- `layer_token_fraction`
- `estimated_block_savings`

`estimated_block_savings` is deliberately a **logical block-work proxy**, not an exact FLOP or latency claim. Frozen tokens still incur K/V projection while any later token remains active. Use the profiler for wall-clock measurements.

## Profiling

Run:

```bash
python scripts/profile_mixture_depth.py --layers 6 --dim 32 --ctx 16 --d-ff 64 --threshold 0.02 --min-depth 2
```

The script emits JSON containing full-depth and adaptive mean/median timings, wall-clock speedup, and the final depth telemetry. Benchmark with representative context lengths and thresholds before enabling routing in a production path.

## Safety and compatibility

- The existing `TinyTransformer` remains unchanged and full-depth by default.
- Training/backprop remains full-depth.
- Snapshot interchange remains unchanged because the router owns no model weights.
- No NumPy or Torch dependency is introduced.
- KV-cache decode is intentionally not used by the router; routing decisions are recomputed per window so depth state cannot silently desynchronise from the cache.
