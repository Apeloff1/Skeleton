# Offline fair-stream admission and crash-safe reconciliation

This feature belongs to the canonical model runtime in
skeleton/ai/model_runtime/fair_stream_queue.py. It does not create a second
inference service, provider boundary, scheduler authority or GPU allocator.
It reuses the existing IterationScheduler token-quantum contract.

## User operation

The installed skeleton-local-fair-stream command reads a bounded JSON
request from standard input and emits one deterministic plan, the exact
execution leases and an integrity-checked continuation checkpoint. It never
accepts prompts, weight bytes, provider credentials, model output or executable
code. The caller runs the admitted work through the existing guarded local
runtime, and reports the **actual** number of tokens executed for each lease.

A sample input for operator-supplied/simulated capacity:

~~~json
{
  "schema": "skeleton.ai.fair-stream-command.v1",
  "requests": [
    {
      "request_id": "world-42",
      "tenant_id": "game-studio",
      "phase": "prefill",
      "remaining_tokens": 2048,
      "bytes_per_token": 8192,
      "priority": 0
    }
  ],
  "checkpoint": null,
  "acknowledgments": [],
  "cancellations": [],
  "envelope": {
    "available_ram_bytes": 1073741824,
    "reserved_ram_bytes": 536870912,
    "token_budget": 512,
    "stream_slots": 2,
    "pressure_ppm": 0,
    "thermal_hold": false,
    "measurement": "simulated"
  },
  "token_budget": null
}
~~~

Run skeleton-local-fair-stream with standard input redirected from request.json
to obtain a plan. The output is a **planning receipt**, not proof that
inference ran. An operator payload cannot impersonate OS telemetry by
setting measurement to os_probe.

For measured capacity, pass --live and set envelope to null and
token_budget to the desired per-cycle ceiling. The CLI probes the canonical
offline app's OS RAM/container/CPU/pressure module and the Linux CPU/SOC
thermal-trip module. If no thermal trip is measured, the output says
thermal_trip_measured: false; it does not claim thermal safety. This
observation does not replace the native backend's allocation guard or model
identity validation. No GPU/VRAM headroom is assumed from CPU RAM.

## Fairness, pressure and limits

Tenant order rotates each cycle, independent of a tenant's priority. Within a
tenant, bounded aging eventually raises waiting work above repeatedly
admitted high-priority work. Each request gets at most one slice per cycle.
Decode is bounded to one token, prefill to the configured quantum. All slices
consume both the measured token budget and the declared bytes-per-token
memory envelope. bytes_per_token must be derived from the actual pinned
model/KV layout by the caller, not guessed as universal. If that quantity is
unknown, the caller must refuse execution rather than supply zero.

A high pressure reading shrinks token and stream budgets. A thermal hold or
critical memory pressure grants zero leases. Physical RAM is not reserved by
the planner; execution must re-probe, reserve and verify through the actual
backend immediately before allocating. The CLI does not launch inference,
mutate model state, send telemetry or open the network.

The queue is bounded to 4096 requests, 64 simultaneous stream leases and a
finite token budget. IDs are UTF-8 and reject control characters. Duplicate
requests and unrecognized fields fail closed.

## Crash and replay

A checkpoint includes exact request state, bounded wait counters, cursor,
round, pending leases and a canonical SHA-256 integrity digest. This digest
detects accidental corruption; **it is not authentication**. The operator
must store the checkpoint in an authenticated and atomic local custody store
when handling untrusted actors. No storage is silently created by this CLI.

A pending lease remains pending after restore. A subsequent plan is refused
until the execution owner reconciles every pending lease with an
acknowledgments record. Zero consumed tokens requeues work; a partial
acknowledgment decrements only verified progress. An acknowledgment is not
accepted twice. Cancelling a pending request is refused until the execution
owner establishes whether a kernel completed it. This avoids duplicate
inference on ambiguous crash recovery. An external owner must supply actual
execution receipts; the scheduler cannot verify an untrusted claimed count.

## Qualification

The canonical tests in skeleton/testing/test_fair_stream_queue.py cover
tenant fairness, priority aging, decode quantum, pressure and thermal holds,
memory accounting, bounded capacity, pending lease fences, cancellation,
partial completion, deterministic replay, corruption, forged lease binding
and CLI request/response validation. Test budgets are explicitly simulated.

Run these commands after completing the implementation:

~~~sh
python -m pytest -q skeleton/testing/test_fair_stream_queue.py
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
python scripts/check_provider_bootstrap.py
~~~

A passing unit suite is not native hardware qualification. Before enabling
actual GPU scheduling, bind this planner to the existing native runtime
allocator and run macOS Metal, Windows WDDM and Linux CUDA/ROCm hardware
tests with p95/p99 latency, memory pressure, cancellation and crash-recovery
measurements. Do not interpret a plan as a device allocation or claim that
host read-only mmap is coherent with GPU caches.
