# CPU thermal sensor inventory continuity

A positive CPU thermal trip observation binds the controller to a complete sorted set of kernel zone names and sensor kinds. If any previously observed CPU/SOC zone disappears, changes type or is substituted, the controller latches a hard thermal hold. A later cool reading from another zone cannot erase the missing sensor's last-known risk. A fresh controller and independently verified app reauthorization are required; an in-flight lease must not auto-retry.

An incomplete trip inventory is not reported as `trip_measured`; every CPU/SOC zone must have a valid trip. This check is applied to simulated regression fixtures and the real local CPU telemetry adapter. It does not qualify physical hardware, GPU or M-chip execution. OS probes remain observational and exact-head CI/security and focused tests are mandatory before promotion.
