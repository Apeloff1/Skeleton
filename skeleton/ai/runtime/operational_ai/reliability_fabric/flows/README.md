# Offline AI reliability flow plane

This flow implementation composes real local SupervisedAI and ExecutionSpine interfaces with independently supplied caller/model evidence. Key components include the pinned nine-gate preflight, exactly one real native supervisor call, SQLite-based read-only replay, bounded quota and rate admission, monotonic deadlines, immutable audit receipts, single-use HMAC memory consent, tool-intent approval, stream credits, model-source custody, explicit resource observations, ordered restart and a non-automatic release gate.

The separate AssuredSupervisor is opt-in; it does not bypass the canonical GGUF production service, copy its chat database, or silently enable high-risk tools. If native generation fails after reservation, its effects are uncertain: token reservations remain pending and the circuit records failure until operator reconciliation. There is no automatic repeat of an uncertain request.

The focused test suite uses an explicitly named FakeWorker to exercise validation and orchestration. Such tests do not prove a real model loaded or generated text. Real rights, source digest, laptop device E2E, cross-process durability and exact-final-SHA security/CI remain independent mandatory release requirements.
