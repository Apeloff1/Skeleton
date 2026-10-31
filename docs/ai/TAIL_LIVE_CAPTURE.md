# Live local inference timing instrumentation

`LiveTailCapture` provides the canonical execution-owner event seam:
`begin`, `first_token`, `complete`, and `abort`. It uses a monotonic
clock and the existing platform-aware local RAM/swap/CPU resource probe.
The CPU thermal controller reports **unavailable** when there is no
measured trip-point evidence; GPU fields remain unknown rather than
being fabricated from system RAM. The resource probe is read-only.

The bounded state machine rejects duplicate requests, impossible timestamp
order, premature completion, invalid token counts and unbounded active
streams. A failed or aborted inference is not recorded as a completed
latency sample. The canonical `LocalTailProfiler` produces p50/p95/p99,
serial throughput, source-bound digests and SLO observations; fewer than
100 real samples or unknown thermal sensors do not certify qualification.

A trusted native/provider backend must call these hooks at its actual
execution boundaries and validate token counts with its own tokenizer.
Operator-supplied JSON and injected test probes cannot certify measured
hardware. Synthetic tests use injected clocks and resources and always
carry `evidence="simulated"`. This module does not claim a device,
GPU memory transfer, cross-process reservation, model quality, or release
qualification.
