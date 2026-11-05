# admission_queue — production AI reliability boundary

**Layer:** Strict model-bound offline AI operational evidence, not a game
feature or a synthetic native model. Each record includes explicitly provided
tenant, subject, model digest, monotonic lifetime, resource ceilings, operator
approval and source identity.

## Domain-specific required fields

- `depth`: `int`, fixed schema bound
- `ceiling`: `int`, fixed schema bound
- `deadline_ns`: `int`, fixed schema bound
- `now_ns`: `int`, fixed schema bound
- `priority`: `text`, fixed schema bound

## Semantic security guarantees

- Bound queue depth before allocation.
- Refuse work past deadline.
- Priority cannot be assigned by untrusted model text.

## Execution order

1. Source record must be from an independently authenticated operator,
   supervisor, kernel/device probe or approved model manifest.
2. Strict canonical JSON and closed nested schema checks occur first.
3. `policies/admission_queue.py` enforces all cross-field conditions.
4. The caller-model adapter refuses mismatched tenant, subject or model epoch.
5. Run all 22 committed examples against real Python code before any promotion.
6. Verify the external model/rights/device/SQLite evidence independently.

An admitted claim is not a cryptographic proof that any external hardware,
source, workflow or model result is genuine. No arbitrary shell/network tools
or automatic model replacement are authorized by this boundary.

## Threat regressions

- Missing or unknown record properties never silently default to success.
- NaN, coercion, invalid Unicode and resource overruns are denied.
- Expired evidence, unapproved source and mismatched scope must hold.
- Cases `18`, `19`, and `20` exercise domain-specific semantic faults.

**Release:** Final exact-head CI/security, native GGUF inference, device E2E,
model rights, real installation and independent review remain separate holds.
