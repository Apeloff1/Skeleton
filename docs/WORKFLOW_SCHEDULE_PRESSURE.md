# GitHub Actions schedule-pressure inventory

The repository has hundreds of individual Actions workflow definitions. Scheduler pressure must be assessed separately from correctness, release gates, and true GitHub-run telemetry.

Run a bounded, read-only inventory directly from the checkout:

```bash
python scripts/workflow_schedule_inventory.py --top 50
python scripts/workflow_schedule_inventory.py --json > workflow-schedule-report.json
python -m pytest -q tests/test_workflow_schedule_inventory.py
```

The reporter enumerates ordinary `.yml` / `.yaml` files under `.github/workflows`, ignores symlinks, and uses conservative lexical extraction of top-level `on.schedule` cron entries. Only daily expressions with ordinary minute and hour selectors and wildcard date fields receive numeric counts. Weekly, monthly, exotic or malformed cron expressions remain `null` with an unknown marker; they are never interpreted as zero.

Numbers are **scheduled trigger configurations per nominal UTC day**, not billed runner minutes, actual completed workflows, branch-specific dispatches, event-driven jobs, or matrix dimensions. GitHub may delay/drop scheduled runs. Do not use the inventory as a release-qualification receipt.

## October 14 cleanup boundaries

- Repository Bots changed from 24 nominal scheduled invocations/day with four matrix jobs each (96 jobs/day) to four invocations/day with max-parallel two (16 jobs/day). The configured job reduction is 80/day.
- Four noncritical fallback workflows were staggered: PR Churn Control 288→96/day, PR Obsolete Run Drain 144→48/day, Branch Archive 144→48/day, Auto-Merge Control Plane 288→96/day. These four reduce nominal workflow wakes by 576/day.
- The combined estimate is 656 fewer configured scheduled job or workflow executions per day, without treating those unlike counts as observed runner capacity or unique incident resolution.
- Five-minute Queue Drain, Branch Flow, and Branch Clean, their fail-closed guards, and all security/release validations were preserved.
- Idle CI Watchdog no longer retries intentionally cancelled runs or creates repeated issue comments on failed retries; it can still retry eligible timed-out non-security runs once.

The inventory is observation only. Historical workflow-run deletion belongs to the existing governed Actions Housekeeping CLI, not this script. Unknown schedule semantics, required-check changes, CI failures, or elevated queue pressure must be reviewed before additional cadence changes.
