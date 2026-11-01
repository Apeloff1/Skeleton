# Full thermal-zone coverage for in-flight CPU authorization

A healthy CPU thermal zone does not attest other CPU/SOC zones. Studio C's
in-flight pressure guard now requires a measured trip temperature for **every**
CPU/SOC sensor returned by the canonical OS probe. A missing zone, unknown
trip, malformed sample, or unexpected vendor probe exception causes HOLD.
Hysteresis remains conservative and a measured over-temperature still holds.

The app lifecycle never exposes a positive quantum count after quarantine and
routes resume through the same terminal-state fencing as other transitions.
Neither change certifies GPU, Metal, ROCm, M-chip or device hardware. Simulated
regressions are not evidence of production qualification. Missing thermal
telemetry must be addressed with trusted platform-specific sensing, not an
invented threshold or a policy bypass.
