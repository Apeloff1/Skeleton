# Conservative long-context pressure latch

`LongContextPressureLatch` is a process-local, non-authorizing hysteresis
diagnostic over the existing host/cgroup/event telemetry fusion. It rejects
missing fields, extra authority keys, false attestation, malformed counters,
unproven baselines, non-normal CPU/memory/thermal/energy pressure, OOM,
throttling, and unkeyed-digest mismatches. A digest is not a signature.

State transitions: hold -> warming -> repeated_normal_observed; any
non-normal/invalid sample resets to hold. A monotonic-clock regression or
excessive gap resets the streak. Forks reject inherited locks. Restart
starts from zero; no disk state or replay proof is claimed.

`head-observe-latched` is a one-shot, payload-free diagnostic that does not
open the spool and cannot itself reach repeated-normal. Even repeated-normal
never authorizes inference, hardware, memory, KV, disk, or tokens. Backend
authorization and independently qualified device/thermal/energy evidence
remain mandatory. Unknown hardware telemetry remains a hold.
