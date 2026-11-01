# OS-backed local KV tier pressure control

`KVLiveTierController` composes the canonical KV page manager, the
existing source-bound tier planner and the app's real RAM/swap/disk
resource probe. It derives CPU pressure conservatively from RAM use,
kernel pressure and swap occupancy. GPU telemetry is always **unknown**:
this path never infers VRAM from unified memory or claims a GPU transfer.
Only CPU-to-NVMe demotion is eligible when pressure and disk reserve
policy allow it. The real KVStorageAdapter must implement the actual
page move and enforce backend quotas and storage security.

The controller re-probes immediately before applying a plan. Worsening
RAM/disk headroom, stale or out-of-order telemetry, changed source
identity, or unknown capacity rejects the move. The canonical manager
also checks page identity, size, pin count and adapter results under
its KV lock. This does not reserve disk across processes or prove a
race-free GPU/Metal/ROCm implementation.

Tests inject a simulated resource probe and opaque storage adapter.
Injection requires explicit `simulated=True` and cannot qualify
hardware. Production uses the existing platform-gated OS resource
probe and monotonic clock; unsupported platform sensors remain
conservative, not fabricated.

The second OS probe must also confirm that effective CPU pressure has **not
increased**, even if available RAM and disk bytes are unchanged. Swap churn
or kernel pressure can worsen independently of byte headroom; such changes
fail closed before any KV storage adapter move. Synthetic tests exercise
worsening swap pressure with stable RAM/disk readings.

## Fork-safe migration ownership

The CPU/disk KV migration controller now binds itself to its creating process. `plan_live` and `apply_live` check process identity before acquiring a potentially inherited lock or touching the KV storage adapter. A forked child or failed PID probe latches quarantine; it must reopen and independently verify manager, storage, journal and authorization before moving pages. No implicit replay or GPU/M-chip qualification is granted. Cross-process disk allocation still requires the independent durable journal and storage backend enforcement.
