# Live CPU stream pressure gate

The canonical `python -m skeleton.ai.model_runtime.fair_stream_cli --live`
command now samples RAM, CPU and storage headroom and combines the existing
Linux cgroup, I/O PSI, CPU throttle, swap churn, reclaim and thermal controllers.
The same long-lived sampler preserves hysteresis within one CLI process.
An OS probe establishes **advisory** capacity only, never a reservation.

A missing auxiliary sensor constrains each observation to one stream and a
128-token planning quantum. A measured OOM event, thermal hold or exhausted
storage reserve yields zero dispatch slots. Other pressure controllers reduce
admission without claiming measured GPU residency or unified-memory coherence.
No host-wide or cross-process reservation is implied. No model is loaded by
the CLI; only the trusted execution owner can dispatch a durable permit.

These tests use explicitly simulated host probes and do not qualify Metal,
CUDA, ROCm, Windows, energy sensors or actual model throughput. Re-probe at
dispatch, retain source-bound checkpoint and independent watermark custody,
and enforce backend memory quotas and cancellation before executing work.
