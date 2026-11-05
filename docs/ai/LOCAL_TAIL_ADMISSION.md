# CPU tail-latency admission governor (integration candidate)

A deterministic CPU worker-slot controller consumes canonical
`LocalTailProfiler.summary` receipts. It requires at least 100 source-bound
measured observations, known thermal status, and fresh available RAM. Simulated
or unknown telemetry cannot increase concurrency. p99 regressions reduce
admission, three good windows are required for a single-slot increase, and
memory headroom always caps the grant.

The module is a planning component, not a hardware probe or a reservation.
Its checkpoint SHA detects accidental corruption, not hostile edits. The
embedding canonical runtime must bind trusted telemetry provenance, atomically
persist generation/high-watermark, re-probe RAM before actual allocation and
enforce real worker limits. No CUDA, Metal, ROCm, WDDM or physical-device
qualification is claimed. All current tests are simulated.
