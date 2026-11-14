# Fork-safe live CPU stream budget observations

The live fair-stream sampler holds an RLock and mutable hysteresis state for
thermal, cgroup, I/O, CPU throttle, swap churn and memory reclamation. A child
created with `fork()` cannot inherit trustworthy controller history or
authorization to sample using a parent's lock.

`LiveStreamBudgetSampler` binds its construction process ID and checks it
before acquiring its lock or calling ANY hardware/resource probe. Unknown,
malformed or changed PID fails closed. Children must construct new app-owned
samplers and gather fresh evidence; no parent budget, measurement, GPU claim,
or CPU admission is inherited.

This is not a cross-process allocation reservation or a malicious same-UID
process isolation boundary. Actual native backend admission still requires
fresh OS pressure rechecks and independent resource limits.
