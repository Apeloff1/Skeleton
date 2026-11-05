# Offline power and thermal admission — Studio C

This is a dependent addition to the measured CPU topology/worker planner.
Run it without network access or model weights:

    python -m skeleton.app.offline_energy_budget --max-workers 8

Linux reads actual power-supply sysfs status and CPU-labelled thermal zones.
macOS uses the fixed system pmset battery command and leaves CPU thermal
unavailable without an authorized sensor. Windows reads GetSystemPowerStatus
and leaves CPU thermal unavailable. Unknown evidence remains explicitly
unknown, never a fabricated safe temperature or battery percentage.

The energy policy can only REDUCE the worker count already admitted by the
measured CPU/memory planner. It does not raise concurrency, override operator
limits, alter clocks, adjust fan curves or claim protection against every
thermal hazard. Critical CPU temperature or battery capacity denies new
background workers; low battery and unknown sensors tighten concurrency.
The result is a deterministic, source-labelled SHA-256 decision receipt.
Callers must enforce the returned limit and handle cancellation/drainage.

This is an operator-level policy, not an on-device thermal certification.
Different chip vendors require separate qualified sensors and thresholds.

Focused canonical tests:

    python -m pytest -q --noconftest skeleton/testing/test_offline_energy_budget.py
