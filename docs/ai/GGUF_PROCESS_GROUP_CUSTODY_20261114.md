# GGUF process-group custody

The local CLI backend previously used Popen.poll to observe leader exit. That
reaped the leader before cleanup, and the early return in termination left
same-group descendants able to retain output pipes or a workspace flock.
On POSIX systems with waitid/WNOWAIT, observation now retains the leader's
PID, cleanup signals its original group before reaping, and the supervisor
drains output only after requesting termination of that group. Reaped PIDs
are never used for signalling. Existing process and resource lease accounting
remains in place.

This contract requires exclusive process wait ownership and a child started
in a new session. It does not contain a malicious child that calls setsid,
prove kernel-level hard termination of uninterruptible tasks, or eliminate
all possible pipe waits. Unsupported platforms retain the earlier cleanup;
Windows Job Object containment and real Windows/device qualification remain
outstanding. Regression cases use real Python subprocesses, not a GGUF model.
