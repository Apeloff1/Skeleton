# Fast CI and archived specialist qualifications

Skeleton uses a small active Actions set, documented in
`.github/CI_SLIM_POLICY.md`. Historical verification pipelines live at
`.github/workflows-archive/`, where GitHub Actions **cannot run them**.

## Ordinary development
Merge Readiness is a short source-syntax smoke check. It is not evidence of
fully playable games, complete E2E, real model training, or passing installer
qualification. Backend Quality preserves scoped application/security
checks. Secret scanning, malware, dependency and workflow-input security
remain active and scoped.

## Specialist validation (restoration required)
The 11 workflows listed by `machine/ci_workflow_tiers.json` have been
reconciled with the slim pipeline. Their archived copies are visibly tagged
`[Specialized]` and carry `workflow_dispatch` only, but **they cannot be
manually dispatched while archived**. To use them, restore the selected
workflow under `.github/workflows/` in an approved, narrowly scoped change,
dispatch it at the exact intended commit, verify reports, then archive it
again when done. Alternatively execute equivalent commands locally and
retain their exact-source receipts.

Backend Quality contains optional explicit-dispatch Jeeves/game and
adversarial suites. Use their full qualification output before publishing.

## Honest release acceptance
Unrun, cancelled or failed specialist checks never count as passed.
A completed game release still requires independent end-to-end playthroughs,
story/film review, checkpoint inference, installer builds, and platform-specific
qualification. This CI inventory is a workload policy, not a P0 signoff.

Validator: `python scripts/check_ci_workflow_tiers.py`.
Test: `python -m unittest tests.test_ci_workflow_tiers`.
