# Kernel-derived Linux thermal admission

The existing local inference sampler reads bounded Linux sysfs thermal zones
and their measured critical/hot trip temperatures. A zone within 15°C of a
declared trip point reduces concurrency; within 5°C is critical and pauses
background work. The adaptive controller retains its existing cooldown and
hysteretic recovery.

Missing, malformed or uncalibrated trip data is unknown, never interpreted as
a healthy temperature. No guessed CPU/GPU temperature, Apple M-chip thermal
state or battery power metric is emitted. This probe cannot qualify a device
or replace OS-level thermal safeguards.

Tests: `python -m pytest skeleton/testing/test_linux_thermal.py -q`.
