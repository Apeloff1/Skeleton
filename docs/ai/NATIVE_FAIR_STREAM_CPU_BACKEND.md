# Native CPU fair-stream result backend

This integration connects the actual `NativeLLMRuntime` tokenizer and
`generate_sequence` execution graph to the encrypted
`SealedFairStreamResultVault` and signed `FairStreamExecutionJournal`.
It is not a simulated provider, GPU qualification, Apple Metal attestation or
consumer-device certification.

The authenticated app creates a `NativePromptRegistry` for its canonical
session, pins prompts through `stage_native_cpu_prompt`, and submits the
matching tenant-owned `StreamRequest` to
`OfflineAdaptiveDispatchService`. The app must authenticate the caller
*before* staging; neither a request ID nor a stream checkpoint is an ACL.

The app opens separate private SQLite files for result and execution-journal
custody, retains independent execution/custody/result keys, and calls
`bind_native_cpu_result_owner`. The returned journaled owner is supplied to
the guarded dispatch service. The session's independent high-watermark must
already be provisioned; no component here creates or resets it.

The native backend requires an exact CPU execution receipt, immutable model
and tokenizer digests, a lossless prompt tokenizer roundtrip, exact tenant,
lease, generation and checkpoint bindings, sufficient KV/context budget, and
bounded output bytes. It consumes the one-use prompt grant before invoking
the real transformer. Any exception after journal RUNNING is outcome-uncertain:
never retry automatically, even if the prompt remains available elsewhere.
An operator must separately reconcile a *committed* receipt.

The prompt registry is RAM-only by design. After a crash, it cannot restore
pending prompts or grant a retry. Encrypted output is stored only by the
vault. No prompt plaintext, tokens, operator keys, or encryption keys belong
in scheduler checkpoints, logs, PRs or telemetry.

Focused simulated CPU validation:
`python -m pytest -q skeleton/testing/test_native_fair_stream_backend.py`
plus the existing fair-stream dispatch, journal and vault regression tests.
Actual hardware, performance, device and release qualification remain held.

The app binding now requires a canonical `LiveStreamBudgetSampler` and a
selected storage volume. `NativeTokenPressureGuard` checks pressure at
native runtime interrupt checkpoints (including inside transformer compute),
stops on missing evidence, RAM pressure, thermal hold or probe exhaustion,
and retains a stopped state after any failure. A stop is not a successful
completion or a retry permit. The outer journal must reconcile the uncertain
RUNNING intent through the authorized recovery path.
