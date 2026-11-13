# GF-M: GameForge soak harness and perf regression gates

`skeleton/perfgate` (mirrored byte-for-byte in `skeleton/ai/perfgate`) drives a
GameForge workload repeatedly and gates it on absolute budgets and on relative
regression against a stored baseline. Stdlib only; no network, no Godot binary.

## Run

```bash
PYTHONPATH=. python -m skeleton.perfgate \
  --workload forge_walk:soulslike --iterations 20 \
  --budgets skeleton/perfgate/budgets.default.json \
  --baseline perf/baseline.json        # optional
# refresh a baseline (review the diff before committing it):
PYTHONPATH=. python -m skeleton.perfgate --workload forge_walk:soulslike \
  --iterations 30 --write-baseline perf/baseline.json
```

Exit codes: `0` pass, `1` gate failed (budget, regression, or soak aborted after
consecutive errors), `2` usage/config error. `--json` prints one summary line.

## Pieces

| Module | Role |
|---|---|
| `soak.py` | `run_soak(name, fn, SoakConfig)` — warmup, iteration and wall-time limits, abort on N consecutive errors, injectable clock |
| `stats.py` | p50/p95/p99/max/mean, error rate, `drift_ratio` (mean of last third / first third — catches leaks/slowdown over a soak) |
| `budget.py` | JSON budgets `{"version":1,"workloads":{name:{metric:limit}}}`; unknown metrics rejected |
| `baseline.py` | versioned baseline snapshots, relative compare (default 20% tolerance, 2 ms noise floor), reports regressions / improvements / missing / new workloads |
| `workloads.py` | `forge_walk[:era]` (wraps `skeleton.forge.walk_cli.walk_once`, same entry as the CI GameForge walk) and `noop` |

## Measured (box, 2026-10-31, main @ shallow clone)

`forge_walk:soulslike`, 10 iterations: p50 12.6 ms, p95 13.3 ms, max 13.6 ms,
drift x1.01. Default budgets (p95 2 s, max 5 s, 0 errors, drift ≤ 2.0) leave
headroom for slow CI runners.

## CI

No workflow is changed by this PR. To wire it into the "Skeleton GameForge" job,
add `skeleton/testing/test_perfgate.py` to the pytest list and a
`python -m skeleton.perfgate --workload forge_walk:soulslike --budgets ...` step.
That is left for an owner with workflow rights.
