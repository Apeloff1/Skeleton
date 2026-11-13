# Native model capacity and crash-fenced admission — 2026-11-02

## Scope

This change is limited to **AI model operation**, not the game-production plane. It adds an independently reviewable runtime mechanism to stop two independently started GGUF processes from simultaneously claiming the same model memory allocation. The preceding model code checked host/cgroup memory as a single-process point-in-time estimate. That is not global concurrency control: two loaders can simultaneously observe enough RAM and both allocate, potentially crashing the service before conversation requests are recoverable.

This plane is a conservative, owner-scoped RAM/worker admission contract. It is not GPU VRAM validation, a distributed cluster scheduler, a machine-wide quota across distinct Unix users, model quality evidence, or an OpenAI API provider fallback.

## Execution order

1. Independently approved model manifest has the exact digest, shard sizes, rights, context ceiling and minimum memory.
2. Operator selects a root directory for the capacity ledger (default is a private 0700 directory inside the kernel's user-home path). Every directory component is opened with `O_DIRECTORY|O_NOFOLLOW` and the target root is UID-owned, private and non-symlinked.
3. Under a kernel `flock` of `admin.lock`, the policy is compared exactly. Different slot budgets cannot reinterpret old allocations.
4. A request reserves `max(manifest.minimum_memory_bytes, 2 * model_total_bytes + safety_margin)` bytes. The broker sums **actually held** model slot locks and rejects insufficient total budget, then verifies Linux host+cgroup headroom before expensive model loading.
5. `model-slot-NN.lock` stays exclusively locked by an open descriptor for the complete native model lifetime. The first allocation creates a hash-checked private receipt bound to the manifest SHA, model SHA, principal digest, PID, boot identifier and PID start tick; the kernel-held lock, not a remembered PID, is the authority for active occupancy.
6. In isolated mode the child inherits that **specific** lock descriptor using `pass_fds`. If the parent disappears while native C++ is still running, the child retains occupancy. This prevents another model from being loaded against the same budget until the child actually exits.
7. A live `AdmittedBackend` checks the exact private lease immediately before reservation and generation. The executing model ID must still agree with the original capacity slot ID. The capacity lease cannot be used after release.
8. Shutdown closes the model (and waits/kills the native child), then closes the capacity lease, then the broker. This is stack-reversed lifetime ordering. A release must **never call `LOCK_UN`** on an open file description shared with a native child; closing the parent's own descriptor is the correct operation.

## Operator controls

`python -m skeleton.ai.runtime.operational_ai.model.admission.cli --root /private/capacity --slots 1 --budget-bytes 8000000000`

The operator can inspect occupancy, policy and orphaned metadata without inspecting prompts, model outputs, checkpoint paths, passwords, user IDs or private memory. The report is observational, not a quality certificate. Only an independently authorized operator can reconcile an orphan receipt. An explicit approved bootstrap migration may change policy **only before the first model slot ever existed**. Existing slots require a new reviewed capacity root and a controlled cutover; a stale metadata file never gets silently deleted.

Use operator entrypoints with `--capacity-root /private/capacity`. Exact policy must match every loader sharing that root. Direct Python `startup.activate` with no root continues the preexisting compatibility path for older consumers and fixtures: it is **not** evidence of machine-wide capacity coordination. Release qualification must require an actual supervised launch using the capacity-root path.

## Identity limits and remaining holds

- A registry SHA is a corruption checksum, not a cryptographic MAC. Same-UID compromised code is not isolated by ordinary file permissions.
- Kernel locks span independent processes sharing one registry and Unix user; use separate independently governed policies across host users or containers.
- No attempt is made to acquire another worker's CPU, GPU or memory quota by killing it. Occupied slots are never stolen on a timer.
- Orphaned *capacity* receipts may be operator-reconciled when the kernel lock is free. This does **not** authorize retrying any unfinished **inference** or tool effect.
- A model activation failure unwinds the stack and releases its reservation; an unexpected death releases the OS lock, but a remaining native child keeps its lock until exit.
- Every model binary still requires independent license/rights approval, SHA-verified model bytes and tokenizer identity, exact-head CI, real inference, restart replay, process-kill drills, native timing/memory profiling and target-device qualification.
- No approved model weights or genuine 1.9 GB ecosystem archive have been supplied. All new tests use synthetic non-model reservations and process boundaries.

## Focused validation commands

```bash
python -m unittest skeleton.testing.test_ai_model_capacity -v
python -m unittest skeleton.testing.test_ai_model_capacity_extended -v
python -m unittest skeleton.testing.test_ai_model_admission_paths -v
python -m unittest skeleton.testing.test_ai_model_admission_ops -v
python -m unittest skeleton.testing.test_ai_model_capacity_child_lifetime -v
python -m compileall -q skeleton/ai/runtime/operational_ai/model/admission
```

The direct-source integration and CI checks on the **final GitHub SHA** remain mandatory before promotion; passing these focused tests does not certify full native model execution or first install.
