# Operational AI — first usable laptop critical path

**Implementation:** Direct composition of production `ExecutionSpine`,
`SupervisedAI`, authenticated local HTTP, isolated approved GGUF and immutable
source receipts. No new game editor features or synthetic model output.

## New integrated runtime interfaces

- `laptop_runtime/startup.py`: read original installer receipt and hash-verified
  model bytes before calling the canonical real native production activation.
- `laptop_runtime/dispatcher.py`: expose create/turn/history/replay/close/status/
  doctor/identity/pending outbox/event acknowledgement through strict schemas.
- `laptop_runtime/server.py`: reuse hardened loopback-only header, bearer,
  Host, browser-origin, body-size, concurrency and I/O deadline checks.
- `laptop_runtime/client.py` and `client_cli.py`: no proxy or redirect, no
  hosted fallback, stdin prompt, fixed loopback address and request limits.
- `laptop_runtime/turn_bridge.py`: exactly one live supervisor call after
  caller permission and model identity verification; response text must agree
  with its committed output digest and token accounting.
- `laptop_runtime/replay_probe.py`: existing authoritative durable replay,
  no replacement generation on ambiguous native failures.
- `laptop_runtime/cancel_registry.py`: cooperative cancellation only; no
  unsupported claim that blocking native inference was killed.
- `laptop_runtime/device_observer.py`: observed Linux memory/disk readings,
  never a substitute for real laptop qualification.
- `laptop_runtime/qualification/`: adversarial contract suite, explicit
  operator holds and scenario-specific security/threat guides.

## Test only after complete branch publication

```bash
python -m skeleton.ai.runtime.operational_ai.laptop_runtime.qualification.cli
python -m unittest discover -s skeleton/testing -p 'test_laptop_*.py' -q
python -m compileall -q skeleton/ai/runtime/operational_ai/laptop_runtime
```

True model quality, licensing, clean Windows/WSL2 installation, target-device
performance, all mandatory exact-head CI/security checks, independent review,
durable multitenant state and native-cancellation semantics must be separately
verified. No automatic merge or release claim.
