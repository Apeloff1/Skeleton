# Trust-gate operational adapters

These modules turn bounded contract checks into reusable primitives for the
**real** native AI system: byte-stream model verification, byte-exact source
citations, deterministic streaming, process-local quota reservations,
alternating conversation custody, hash-chain verification, loopback admission,
release evidence, deadline inspection and checkpoint metadata.

They do not replace the existing GGUF native runtime, durable SQLite stores,
descriptor-anchored installer, host credential comparison, or CI provider.
They never automatically invoke a model or tool. Tests use real Python
contracts and deterministic fixtures, but not a real loaded model.
