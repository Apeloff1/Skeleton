---
on:
  schedule:
    - cron: "41 */3 * * *"
  workflow_dispatch:
permissions:
  contents: read
  issues: read
  pull-requests: read
  actions: read
safe-outputs:
  add-comment:
engine: copilot
---

# Idle PR Reviewer

Review open pull requests that have changed since the previous sweep. Examine diffs, tests, workflow/security implications, dependency changes, and stale-branch risk. Check whether the PR actually addresses a reported issue. Do not approve, merge, push commits, change branches, or close PRs. Leave a concise review comment containing concrete defects, missing tests, stale assumptions, and verification gaps. Avoid speculative criticism.
