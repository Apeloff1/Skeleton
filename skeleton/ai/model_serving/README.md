# Model serving admission and capacity boundary

This package is a **staging integration layer**, not a production serving API.
It composes with the canonical `skeleton.ai.model_runtime` implementation.

## Trust boundaries

1. A deployment control plane must authorize the model artifact and evaluation
   record and independently determine the expected SHA-256 digests. Neither a
   client request nor a model-generated response may set the expected digests.
2. `admit` checks syntax, exact policy identity, backend name and budgets. It
   does not verify a model, evaluate benchmark semantics or grant authority.
3. `verified_invoke` hashes the supplied bytes before dispatch. It rejects
   empty or mutable byte buffers. Its callback must be installed by the trusted
   deployment composition root, never taken from an untrusted request.
4. `plan_and_invoke` bridges to the existing canonical policy-aware planner.
   It checks the **original** prompt and output budget, not reduced prefill
   estimates. It does not itself load model weights or execute kernels.
5. `CapacityLedger` limits process-local concurrent reservations and total
   reserved tokens. Acquire only after admission. Release on success, failure,
   cancellation, and shutdown; expire abandoned reservations.

## Explicitly missing production guarantees

- Trusted evaluation semantics, signatures, revocation, and promotion gates.
- Durable atomic capacity coordination across processes and replicas.
- Tenant quotas, authentication, per-principal authorization and audit trails.
- Secure model loading, runtime sandboxing, cancellation, streaming and output
  inspection.
- Integration into the actual native inference endpoint and its lifecycle.
- End-to-end tests on a real model plus exact-head CI evidence.

## Regression commands

```sh
python -m unittest discover -s tests -p 'test_model_serving_*.py'
```

No completion sign-off is warranted until the full serving lifecycle is wired,
tested, and independently validated. In particular, a digest match is **not**
proof that an evaluation passed or that the model is safe to deploy.
