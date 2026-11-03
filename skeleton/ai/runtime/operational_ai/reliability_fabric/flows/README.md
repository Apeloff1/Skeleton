# Operational reliability flows for real offline AI

The reliability-fabric flow layer contains source-validated and
identity-bound adapters over the canonical real `ExecutionSpine`,
`SupervisedAI`, GGUF/native inference and private SQLite custody.

It contributes actual bounded behavior: atomic multi-domain evidence
admission, pinned-model preflight, single real supervisor turn, read-only
durable replay, finite quotas, monotonic deadlines, retry-after-effect holds,
content-hash event chains, ordered streaming ACK/backpressure, single-use
HMAC consent, read-only tool-intent lifecycle, restoration custody, model
installer verification, device admission, private-only metrics, circuit
recovery and exact-head release status holds.

**Critical distinction:** A valid operator JSON evidence record is only
a *claim*. The flow source does not independently prove that the attached
model, license, CI status, hardware reading or provider exists. Every
effect-capable adapter must be called by an authenticated operator or
canonical service that supplies the actual evidence. The native-turn wrapper
calls the actual supervisor; focused tests use the clearly labeled
`FakeWorker` interface contract double only.

In-process quota/rate/ledger state is not durable distributed state.
The existing SQLite execution spine and source-bound installer remain
the final authorities; these flows must not silently mutate them from
model-generated text or pretend to replace their guarantees.

## Focused commands

```bash
python -m unittest discover -s skeleton/testing -p 'test_ai_reliability_flow_*.py' -q
python -m unittest discover -s skeleton/testing -p 'test_ai_reliability_*.py' -q
python -m skeleton.ai.runtime.operational_ai.reliability_fabric.cli
```

Target laptop native inference, clean install, Windows/WSL2 compatibility,
checkpoint licensing, independent review, full exact-head security and
cross-process durability remain release holds.
