# Descriptor-pinned Linux CPU thermal telemetry

The CPU/SOC thermal probe now opens every sysfs ancestor, zone and attribute
with no-follow descriptor-relative operations. Every bounded attribute read
checks descriptor/name identity before returning a value. Zone enumeration is
limited to 256; each zone inventory is bounded to 4096 entries and 64 trip
pairs. Missing or mismatched trip temperature/type pairs, symlinked entries,
unexpected matching names, unreadable files and malformed millidegrees deny
the complete sample instead of silently reporting a cool CPU.

The controller's sensor identity baseline, measured-trip hysteresis and
latched hold behavior remain unchanged. Unknown sensors or telemetry cannot
grant CPU execution. This is a Linux telemetry safety contract, **not**
on-device qualification or a GPU/M-chip path. Application execution must
still revalidate pressure and token budgets.

Focused tests: `pytest -q skeleton/testing/test_offline_cpu_thermal_probe_completeness.py`
and the existing tail inflight/pressure guard tests. Exact-head CI and
security review remain required before promotion.

The default probes the real `/sys/devices/virtual/thermal` directory,
not the `/sys/class/thermal` symlink view. A symlinked or unavailable
platform topology returns unknown evidence rather than following a path.
