# Fork-safe local tail telemetry owner

The native/provider CPU timing capture owns mutable request identities,
monotonic observations, a completed-ID replay window, and an RLock. Forking a
process does **not** transfer that evidence or authorize a child to mutate it.

`LiveTailCapture` records the construction PID and checks it before acquiring
the inherited lock on every public state transition and observation:
`begin`, `first_token`, `complete`, `abort`, `snapshot`, and
`active_count`. Missing, malformed or changed process identity fails closed.
The child must construct a new app-authorized capture and start a new session.
It must never claim a parent's in-flight request as completed.

This is a process-ownership guard, not a security boundary against malicious
same-UID processes, device qualification, proof of hardware allocation or a
durable completion journal. Existing RAM, thermal, clock and active-count
guards remain in force. Synthetic regression tests patch PID and replace the
inherited lock with a trap to prove rejection occurs before lock acquisition.
