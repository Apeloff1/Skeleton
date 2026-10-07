---
on:
  schedule:
    - cron: "7 */2 * * *"
  workflow_dispatch:
permissions:
  contents: read
  actions: read
  issues: read
  pull-requests: read
safe-outputs:
  create-issue:
  add-comment:
engine: copilot
---

# Idle CI Investigator

When this runs, inspect recent failed, cancelled, or timed-out GitHub Actions runs. Focus on failures that block open pull requests or main. Correlate failures with the exact commit SHA and changed files. Distinguish deterministic code failures from infrastructure/transient failures. Do not modify code, rerun security gates, dismiss alerts, or merge anything.

For each actionable failure, produce one concise diagnosis with: failing workflow/job/step, exact error evidence, likely root cause, affected PR/commit, and a concrete next action. Create an issue only when the finding is new or materially changed. Otherwise add a comment to the existing tracking issue. Never close issues automatically.
