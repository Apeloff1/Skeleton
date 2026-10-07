# Runtime Lifecycle Integration Notes

## Purpose

Track the remaining integration boundary between command execution and lifecycle control.

## Current boundary

```
CommandService
    -> CommandExecutionLifecycle
    -> ExecutionLedger
    -> evidence / reconciliation consumers
```

## Rules

- Command handlers remain domain adapters.
- Transport layers do not own retry policy.
- Lifecycle state must be deterministic.
- Missing evidence cannot produce completed state.
- Retry decisions remain separate from execution recording.

## Next integration targets

1. Application service construction.
2. Correlation identifier propagation.
3. Runtime tests around success/failure transitions.
4. CI validation of lifecycle invariants.
