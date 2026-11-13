# Audited long-context resume

The operator-facing `window` and `advance` commands now require a complete
bounded checkpoint ancestry audit before returning token IDs or publishing a
new checkpoint. The default maximum is 4096 immutable receipts; callers can
set `--max-checkpoints` (1–100000) explicitly. A missing genesis, mismatched
tokenizer, invalid ancestor or excessive chain fails closed.

The lower-level `next_window` and `advance` primitives remain available to
trusted callers with their own custody policy. For user-facing flows, use
`audited_next_window` and `audited_advance`; never mistake a one-parent
check for full chain verification. This remains content-integrity evidence,
not an authenticated publisher, execution permit, global replay fence,
encrypted KV tensor archive, or device qualification.
