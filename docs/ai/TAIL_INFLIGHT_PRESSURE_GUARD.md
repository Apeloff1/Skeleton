# In-flight CPU pressure guard

The existing tail profiler measures completed inference latency. The new
`InFlightCPUResourceGuard` adds a **cooperative per-token-quantum stop gate**
to prevent a backend from continuing under late RAM, swap, disk, CPU or
measured thermal pressure. The app must call `start()`, then
`checkpoint(generated_tokens=n)` after each bounded quantum and stop issuing
more tokens whenever the state is HOLD or ABORTED. A HOLD can resume only
after fresh measured samples satisfy hysteresis. Terminal states cannot resume.

Only the canonical OS resource and thermal probes are accepted for production.
Injected probes require `simulated=True`, and simulated decisions always set
`continue_execution=False`. No GPU, Metal, ROCm, CUDA or M-chip qualification
is inferred. Unknown thermal trips, missing resource evidence, swap exhaustion,
high CPU load, memory pressure and low disk/RAM cause a conservative hold.

The guard is in-process and does not claim crash recovery or durable execution.
It must be wired behind the existing authenticated journal and resource owner.
After restart, never reconstruct a RUNNING permit from this in-memory state.
A token checkpoint is cooperative and not an OS-level hard reservation; the
backend must enforce quotas and cancellation independently.

Focused validation:
`python -m pytest -q skeleton/testing/test_tail_inflight_guard.py`
plus canonical tail, thermal and offline resource suites. Exact-head CI and
device qualification remain held.


## Explicit pre-quantum admission and completion accounting

Production CPU token loops must call `admit_quantum(requested_tokens=N)`
before each model quantum, inspect `continue_execution`, and cap generated
tokens at `authorized_quantum_tokens`. A fresh OS resource/thermal sample is
taken before granting each quantum; an unaccounted outstanding quantum blocks
completion and a reported token count beyond the granted quantum aborts the
controller. The final application completion count must exactly match the
sum of checkpointed generated tokens or the session quarantines pending
independent execution-journal reconciliation. Simulated measurements never
grant production execution, even when their state says `running`.
These controls are cooperative: the backend must honor the grant and maintain
its own memory allocation and durable execution fences.
