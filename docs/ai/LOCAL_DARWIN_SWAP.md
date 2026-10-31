# Native macOS swap observation

The local inference sampler queries the documented Darwin `vm.swapusage`
structure through libSystem `sysctlbyname`, without shell commands or
hosted-provider access. Reported bytes and utilization are tagged as
measured; absent, invalid or unsupported counters remain unknown.

Swap occupancy is observational and does not modify physical M-chip RAM,
unified memory capacity, kernel swap configuration or Metal residency.
PSI/thermal backpressure is independently measured where supported.
Tests use a clearly labeled simulated sysctl ABI; actual Apple Silicon
qualification requires macOS hardware.
