# Unified offline runtime admission

The historical resource and native weight owners already exist on main.
This integration connects them at an application-facing boundary instead
of copying archived implementations. It is independent of the GameForge
saga branch.

## Existing owners

| Owner | Integrated responsibility |
| --- | --- |
| offline_inventory / WeightShardStore | physical manifest and content-addressed shard verification |
| gguf_preflight | exact SHA, descriptor custody and bounded GGUF framing |
| offline_cpu_budget | measured affinity, quota and memory worker ceilings |
| offline_energy_budget | battery and thermal worker reductions |
| nvml_memory_probe | measured Linux NVIDIA memory, or explicit unavailability |
| device_placement | deterministic whole-shard placement proposal |
| offline_energy_hysteresis | slow recovery and immediate pressure shedding |
| iteration_scheduler | pressure-aware prefill/decode proposals |

The model plan SHA and model identity SHA must be independently retained by
the operator. Inventory verification does not choose a model automatically.
The default preflight checks every selected shard with the existing GGUF
framing owner. Non-GGUF inspection must be explicit; it grants no framing
or tensor claim. The original store and descriptor owners still define
the physical source trust boundary.

## Operator interface

```sh
python -m skeleton offline-runtime preflight --store /private/weights --plan-sha PLAN_SHA --model-identity-sha MODEL_SHA
```

The installed equivalent is `skeleton-offline-runtime`. Replace the SHA
placeholders with actual independent 64-character lowercase digests.

CPU, CUDA and hybrid modes are explicit. Hybrid is a placement proposal
across separate device capacities, not a unified physical memory claim.
Weights assigned to host memory reduce the remaining worker budget.
Each configured device reserve is subtracted before placement.
Missing CUDA evidence cannot silently select a CPU-only backend.
Pressure is the projected occupancy fraction of the selected host/GPU
memory accounting, not measured PSI or a model bandwidth measurement.
Unknown memory, critical energy or stale telemetry block proposals.

A bounded iteration work document contains metadata only:

```json
[
  {"request_id":"decode-1","phase":"decode","remaining_tokens":128,"priority":0,"age":0},
  {"request_id":"prefill-1","phase":"prefill","remaining_tokens":2048,"priority":0,"age":0}
]
```

```sh
python -m skeleton offline-runtime iteration-plan --store /private/weights --plan-sha PLAN_SHA --model-identity-sha MODEL_SHA --samples 3 < work.json
```

The planner uses the existing canonical scheduler, then caps the number
of admitted slices using the independently constrained worker budget.
A slice is a proposed unit of work, not an inference observation.
The CLI revokes its pending proposal before exiting. No printed receipt
is a transferable execution token. Use `--require-candidate` for a
nonzero result when no eligible proposal is available.

## Trusted local application API

```python
from pathlib import Path
from skeleton.app.offline_runtime_preflight import RuntimePolicy
from skeleton.app.offline_runtime_control import parse_work
from skeleton.app.offline_runtime_session import OfflineRuntimeSession

policy = RuntimePolicy(backend="cpu")
with OfflineRuntimeSession(
    Path("/private/weights"),
    plan_digest=plan_sha,
    model_identity_digest=model_sha,
    policy=policy,
) as session:
    work = parse_work(request_metadata)
    observation = session.offer(work)
    candidate = observation["admission"]
    if candidate["status"] == "candidate":
        slices = session.consume(candidate)
        # A separate trusted execution owner must enforce these budgets.
```

The session owns its actual monotonic clock and hardware probing. Repeated
healthy samples are required for recovery. A new offer, expired or altered
proposal, source reinspection, explicit revocation, or session closure
invalidates the prior pending proposal. Fixtures cannot prewarm the
local-probe recovery gate. The lower-level controller is intended only for
trusted in-process callers; a source label is not independent attestation.
Reinspection verifies selected source bytes again and closes the session
if the evidence differs. No process restart inherits a worker grant.

## Qualification and caveats

```sh
python -m pytest -q skeleton/testing/test_offline_runtime_admission.py skeleton/testing/test_offline_weight_inventory.py skeleton/testing/test_offline_cpu_budget.py skeleton/testing/test_offline_energy_budget.py skeleton/testing/test_nvml_memory_probe.py skeleton/testing/test_pressure_iteration_scheduler.py tests/test_native_gguf_preflight.py
python -m compileall -q skeleton/app/offline_runtime_preflight.py skeleton/app/offline_runtime_control.py skeleton/app/offline_runtime_cli.py skeleton/app/offline_runtime_session.py
python -m skeleton capabilities --main-cli-audit
```

The fixture suite includes mocked probe/descriptor adapter cases and real
small content-addressed test bytes. Neither is physical inference evidence.
Actual full-size GGUF inspection, tensor/tokenizer validation, independently
held loader descriptors, licensed model approval, native device allocation,
kernel execution, concurrent resource enforcement, crash recovery, latency,
Windows/WSL2 and mandatory exact-head CI remain separate. The session
does not retain source handles between probes, reserve system resources,
start a model, call a hosted provider, or qualify a device. No release or
merge authorization.
