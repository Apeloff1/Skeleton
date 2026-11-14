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

For authenticated workspace launches, the locked persistent marker is set to
0x01 and flushed before the model gate opens. The exact launch's completion
callback restores 0x00 only after verified zero active members and helper
reaping. If the supervisor dies or termination evidence is unavailable, the
marker remains dirty and a replacement service fails closed, even after the
byte-range lock is released. Standalone children without a workspace lease
have no cross-process workspace claim.

The Windows workflow runs actual helper/descendant subprocess tests on a
Windows-hosted runner and is required by the full regression aggregate.
These tests do not qualify real GGUF outputs, installer integration, Windows
11/WSL2 hardware or driver behavior. A frozen executable without a trusted
CPython helper is denied. Automatic recovery of a dirty marker is intentionally not implemented.
Only a separately qualified operator recovery procedure may clear it after
establishing that all prior native work has stopped. Never clear it merely
because the byte-range lock is available. No unsupported containment fallback.
