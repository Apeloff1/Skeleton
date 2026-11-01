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

## Fail-closed kernel probe completeness

Linux sysfs probing must not silently drop a CPU/SOC zone with an unreadable
temperature, missing type, invalid trip value or unbounded trip inventory.
One incomplete relevant zone invalidates the *entire* CPU thermal sample,
even when another zone is healthy. The in-flight guard therefore receives
unknown telemetry and holds rather than authorizing a token quantum.
Deterministic fake-sysfs tests exercise both complete and incomplete zone
inventories. This is deliberately conservative and does not assert physical
hardware qualification.

## Bounded kernel attribute reads and complete trip inventory

Every Linux CPU/SOC sysfs temperature, zone type and trip type is read through
a bounded binary read (64 or 128 bytes) and strict ASCII decode. Oversized,
malformed or missing attributes invalidate the entire sample; they cannot
allocate unbounded memory or disappear from the measured CPU zone inventory.
Unexpected thermal-zone filename suffixes and unknown trip categories likewise
fail closed. Active cooling trips are included as measured thresholds rather
than ignored. The default Linux sysfs root is a trusted OS input; this is not
a general-purpose secure opener for attacker-controlled directory trees.
