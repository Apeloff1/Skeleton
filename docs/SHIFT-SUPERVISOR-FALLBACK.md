# Shift Supervisor schedule fallback

`Shift Supervisor Control` remains cron-first. GitHub may delay or omit scheduled workflow events during sustained Actions pressure, so the workflow also accepts pushes to the trusted `main` branch as a recovery signal.

The push path is not a second planner. Before checkout, model access, or plan mutation, it checks the canonical plan issue. If that issue was updated within the existing 20-minute freshness boundary, the expensive control steps are skipped. If the issue is missing or stale, the same canonical Supervisor workflow runs both Shift Manager and Secretary, publishes through the same issue/state boundary, and remains protected by the existing concurrency group and permissions.

The fallback intentionally has no pull-request trigger, no write permission to repository contents, no Actions mutation authority, and no direct worker-dispatch path. Normal scheduled Secretary/Manager cadence remains unchanged; the push signal exists only to recover canonical-plan freshness when GitHub cron delivery stalls.
