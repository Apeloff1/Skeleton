# Native CPU pressure evidence must be internally consistent

The native token callback accepts only the canonical `skeleton.ai.live-stream-pressure.v1` observation from the live OS sampler. It checks complete, typed hold flags against the measured stream budget before any additional token may be generated. Hard OOM, thermal, cgroup-memory or disk-reserve holds require zero effective slots. An auxiliary-sensor gap, unmeasured thermal trip or any hold must never grant multiple native streams.

The check rejects missing, forged, contradictory and type-confused provenance. GPU qualification, physical reservation and cross-process admission remain **false**. A mismatch stops the one-use lease and leaves execution outcome uncertain; it is not automatically retried or silently downgraded to permissive telemetry.

This is an additional fail-closed consistency boundary, not device certification, proof of kernel measurement authenticity, or an independent process-level watchdog. Focused tests and exact-head CI/security gates are required before promotion.
