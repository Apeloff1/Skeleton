# Fork-safe native CPU prompt authorization

An inherited Python registry or backend does not inherit a valid CPU execution grant. Before acquiring any Python RLock or inspecting staged prompt bytes, the registry and backend compare the current OS PID with their construction owner. Forked workers and unavailable process identity fail closed, including for claim, revoke, telemetry and execution. The parent retains its one-use grants; a child requires a fresh authenticated session and durable journal authorization.

This is a process-local defense in depth, not a cross-process replay fence. The independent signed execution journal, pressure guard, encrypted result vault and actual model/KV limits remain mandatory. A new process cannot automatically replay an uncertain RUNNING lease. Focused tests and exact-head CI/security remain required before promotion.
