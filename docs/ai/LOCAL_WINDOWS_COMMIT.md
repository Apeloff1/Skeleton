# Windows system commit pressure

The canonical offline inference sampler queries Windows PSAPI
`GetPerformanceInfo` to measure system committed pages, commit limit and
page size. Commit occupancy above 90% reduces concurrency; above 97% is
critical and pauses background inference. The adaptive controller retains
operator ceilings and hysteresis. Missing/invalid native counters remain
unknown, not a fabricated zero. Job-object and physical RAM constraints
continue to apply independently.

This is system virtual-memory commit telemetry, not GPU VRAM, WDDM budgets,
physical RAM expansion or Apple M-chip modification. Tests use a clearly
simulated ABI; Windows on-device qualification remains required.
