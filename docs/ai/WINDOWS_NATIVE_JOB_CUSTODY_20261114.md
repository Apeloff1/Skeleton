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
CPython helper is denied. Each dirty marker now carries a fresh 256-bit launch identity. The operator-only
method prepare_windows_crash_recovery reads that challenge under the workspace
lock; explicit prepare_legacy=True can assign a challenge to an old one-byte or
partial dirty marker without clearing it. After independently establishing that
ALL prior native work has stopped, the operator signs the current challenge and
reviewed evidence SHA-256 with a separately provisioned HMAC key using
issue_windows_drain_approval. The trusted maintenance caller passes this approval
and its independently configured key to recover_windows_crash_marker. It checks
and clears the exact marker under exclusive lock. Approval cannot authorize a
later launch; no inference starts during recovery. The evidence digest binds an
operator attestation, not an OS proof. No automatic or public recovery endpoint
is provided. Do not treat mere lock availability as proof of drainage. No
unsupported containment fallback.
