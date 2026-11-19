# Application in-flight CPU pressure and tail capture

`OfflineTailInFlightSession` wires the canonical in-flight pressure guard to
the measured/simulated tail profiler. The installed app can use the typed
`begin -> first_token -> checkpoint -> complete/abort` lifecycle to publish
payload-free status and timing. A resource HOLD stops new token quanta; resume
requires measured hysteresis. A cross-component telemetry failure quarantines
the controller rather than reporting successful execution.

The backend must check `continue_execution` before emitting tokens. Simulated
probes always return false, even when the simulated state says RUNNING.
This is cooperative CPU execution only, not a physical RAM reservation,
GPU/M-chip qualification or durable restart contract. Persist execution intent
and result receipts using the existing authenticated journal; never restart
a partially executed request automatically.

Focused tests: `python -m pytest -q
skeleton/testing/test_offline_tail_inflight.py
skeleton/testing/test_tail_inflight_guard.py`. Complete exact-head CI,
thermal/device and integration qualification remain mandatory.

Unexpected CPU guard or platform-adapter exceptions now quarantine the app lifecycle even when they are not a typed pressure denial. The controller attempts a terminal abort and requires durable execution-journal reconciliation before any new request; it never treats an exception as a healthy pressure sample or permits implicit replay. This remains cooperative and does not qualify a GPU or device.
