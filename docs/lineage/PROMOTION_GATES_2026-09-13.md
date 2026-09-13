# Promotion gates — 2026-09-13

## Gate A — provenance

- Source repository recorded.
- Source revision recorded.
- Source path/module recorded.
- Disposition recorded: promote, characterize, adapt, defer, or reject.

## Gate B — architecture

- No application route/framework dependency in kernel contracts.
- No vendor/provider dependency in provider-neutral interfaces.
- External databases remain adapters.
- Runtime ownership and lifecycle are explicit.

## Gate C — resilience

- Bounds are explicit for memory, concurrency, queueing, and retries.
- Failure mode is fail-closed or explicitly degraded.
- Idempotency semantics are defined for retried operations.
- Cancellation does not leak resources.

## Gate D — compatibility

- Existing Skeleton implementation is located before introducing a duplicate.
- Stronger source semantics are captured as tests/contracts before replacement.
- Python/Rust/C# differences are represented as adapters, not accidental coupling.

## Gate E — testability

- Contract tests cover success, saturation, retry, cancellation, and failure paths where applicable.
- No test depends on credentials, external services, local caches, or generated artifacts.
- New behavior is isolated enough for deterministic CI.

## Gate F — delivery

- Changed files are limited to the intended layer.
- Provenance accompanies promoted source-derived behavior.
- No secrets or environment-specific state are committed.
- Merge target is `frontier/consolidation-foundation` unless a later canonical branch supersedes it.

## Immediate application

Apply these gates first to GameForge Rust parity and Jeeves/Prood/Tutolage extraction. Do not wholesale-copy routes, frontends, server frameworks, or persistence implementations merely because they exist in a source repository.
