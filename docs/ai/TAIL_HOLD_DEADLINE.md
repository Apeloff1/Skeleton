# Offline in-flight HOLD deadline

A CPU inference request held by unknown RAM, disk, swap, CPU or thermal
telemetry cannot wait indefinitely. The guard now latches the first HOLD
monotonic timestamp, enforces a bounded operator-configured hold lifetime
(default 120 seconds; hard maximum 1 hour), and transitions to terminal
ABORTED on timeout, clock regression or missing clock evidence.

Repeated failed probes and resume attempts cannot refresh the original HOLD
deadline. Successful hysteretic RESUME clears the hold timestamp only after
the required consecutive good resource samples. A new HOLD after a genuine
RUNNING period starts a new deadline. Both `status()` and `resume()`
check expiry. Terminal abort never reconstructs a permit or automatically
replays model execution after restart. Simulation remains non-authorizing.

This is a cooperative watchdog. It does not forcibly preempt a blocking
native call; the backend still needs independent process cancellation,
execution journaling and pressure monitoring. No GPU/M-chip qualification
or consumer readiness is implied.

Focused regression command (not yet executed):
`python -m pytest -q skeleton/testing/test_tail_hold_deadline.py skeleton/testing/test_tail_inflight_guard.py skeleton/testing/test_offline_tail_inflight.py`
