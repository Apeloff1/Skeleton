# Expiry and stale worker recovery without blind repeats

**Executable scope:** `skeleton.ai.runtime.operational_ai.durable_jobs`

This contract owns the `sweep` boundary of the local AI workload queue.
It uses actual owner-bound SQLite transactions, explicit fail-closed typed
inputs and the existing offline native inference service. It never upgrades
model-generated text into tool authority or chat-store write privileges.

## Operational obligation

Each of the 32 source-controlled acceptance cases in
`durable_jobs/scenarios/sweep/` documents its threat, exact input,
expected disposition and authority boundary. Cases execute live policy
code using a private test SQLite database. Their expectations are fixed
without taking any answer from a model.

Focused command:

```bash
python -m unittest skeleton.testing.test_durable_jobs_domain_sweep -v
```

## Security and release holds

The in-process test fixture is not native-model inference, device evidence,
cross-process custody, secure installation, or full CI qualification.
A successful 32-vector control pass is not an approval to execute untrusted
tool requests, ship model weights, permit hosted fallback, or bypass source
identity, audit, lease, capacity, license or operator review gates.
