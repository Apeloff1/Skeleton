# Windows native Job Object custody

The Windows GGUF launch path now uses an unnamed, noninheritable kernel Job
Object with KILL_ON_JOB_CLOSE. A trusted CPython helper starts in isolated
mode and waits on a private pipe. Only after assignment and member
verification does the supervisor release the gate, permitting the helper
to launch the pinned native command without a shell. A failed assignment
never releases the gate (including nested host-job restrictions).
Normal cleanup terminates remaining job members and waits for the active
member count to reach zero. Parent death closes the job handle and requests
kernel termination. No breakaway policy is enabled.

The Windows workflow runs actual helper/descendant subprocess tests on a
Windows-hosted runner and is required by the full regression aggregate.
These tests do not qualify real GGUF outputs, installer integration, Windows
11/WSL2 hardware or driver behavior. A frozen executable without a trusted
CPython helper is denied. The supervisor's existing byte-range lock can be
released by process death before the kernel has fully drained its job;
cross-process simultaneous model exclusion during that interval requires
additional platform qualification. No unsupported containment fallback.
