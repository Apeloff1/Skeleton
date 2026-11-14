# Completion-time pressure sampling for local tail telemetry

The canonical `LiveTailCapture` now observes CPU/RAM/swap/thermal resources
at **both** request start and completion. The profiler records the conservative
envelope: minimum available RAM/swap, maximum CPU load, and a thermal hold if
either observation measured one. An unknown thermal sensor stays unknown
unless a measured hold was observed; partial GPU evidence is discarded rather
than extrapolated. No sample qualifies native GPU execution or memory residency.

If the completion probe fails, the active request remains incomplete and
cannot enter a successful tail profile. The execution owner must reconcile
the completed model result separately; profiling failure is not a license
to re-execute it. Admission must still use a fresh OS observation immediately
before any subsequent dispatch. The two endpoint observations are not a
continuous peak-memory or thermal trace and are not physical reservations.

The deterministic tests use injected simulated resources only; no CPU, M-chip,
Metal, CUDA, ROCm or consumer-device qualification is claimed.
