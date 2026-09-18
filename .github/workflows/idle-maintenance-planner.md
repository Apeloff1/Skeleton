---
on:
  schedule:
    - cron: "13 5 * * *"
  workflow_dispatch:
permissions:
  contents: read
  issues: read
  pull-requests: read
safe-outputs:
  create-issue:
  add-comment:
engine: copilot
---

# Idle Maintenance Planner

Analyze the repository backlog, stale branches, open PRs, duplicate issues, missing tests, and documentation drift. Build a dependency-aware maintenance queue. Prefer work that directly resolves existing reported problems. Identify safe, bounded tasks suitable for an autonomous coding agent and explicitly flag tasks requiring human/admin action. Do not close issues, delete branches, merge PRs, modify security controls, or make speculative roadmap decisions. Create one planning issue only when the queue materially changes.
