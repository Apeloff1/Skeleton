# Lean CI, build and email-noise policy

Automatic GitHub Actions workflows stay inside a 20-file cap. Signed master-plan
evidence workflows may also live under .github/workflows when their only trigger
is workflow_dispatch. Specialized qualifications in .github/workflows-archive
stay inactive.

## Trigger architecture
- Merge Readiness: PR-only smoke check (no duplicate main push).
- Backend Quality: scoped application and policy-change verification.
- Secret scanning, Malware Gate, Repository Hygiene: PR and main protections.
- Workflow Input Security: active-workflow security validation on relevant changes.
- Dependency Review: dependency or action manifest changes.
- Artifact Policy: PR, weekly and manual only; no duplicate main push.
- Reproducible Release: tags and manual only.
- Branch Clean: manual only, reducing risky automatic branch churn.
- Auto-Merge Control Plane: event-driven from PR merge-readiness success.
- Queue Drain: hourly and manual; no workflow-completion fanout.
- Actions Housekeeping: twice daily and manual.
- Automation Traffic Manager: every six hours and manual.
- Repository Supervisor / Secretary: managed dispatch rather than unbounded cron.

## Security and release qualification
The lightweight PR smoke check does not prove full integration, game playthrough,
model inference, Windows installer, or release quality. Run domain-specific,
full E2E and release suites before releasing. The active-workflow security gate
retains input interpolation, third-party-action allowlist, permissions, trigger
fanout, concurrency collision, workflow-run consumer, secret hygiene, and bot
activation scans. Obsolete contract tests requiring archived workflow YAML at
the former active path are excluded from the active gate, NOT deleted.

## Email
GitHub Actions failure notifications originate from GitHub. Workflow YAML cannot
globally disable recipients' failure emails. Control those with GitHub notification
settings or a Gmail filter. Keep current-head failures visible; archive old noisy
failure emails without deleting them.
