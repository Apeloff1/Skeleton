# Current Task Solutions Draft

Enterprise-grade scrutiny of open issues and the P1 cascade.
Generated for review. No production code changes in this pass.

## P1 cascade

All 30 previously blocked P1 items advanced to `ready`.
Root cause of the block was P1-INTEL-03 and P1-AUTO-01 remaining `blocked`
after their own dependencies were `done`. Once those two were marked `ready`,
the full dependency closure (INTEL, AUTO, PROD, LEARN, REL, DIST, PROM)
became satisfiable in one cascade.

Action: implement in dependency order starting at P1-INTEL-04 and P1-AUTO-02.
Do not start PROM until REL and DIST acceptance tests exist.

## Open issues

### #4133 Backend: 8 route modules silently skipped at boot
- Severity: high
- Root: import failure swallowed by boot skip path
- Draft: fail-closed on route import in non-dev profiles; log the exception
  and refuse ready until the module imports. Add a boot test that asserts
  zero SKIPPED route imports on the canonical profile.

### #4132 Integration Smoke: uninspectable HTTP route
- Severity: medium (advisory until #4129)
- Root: cortex_mount_guard cannot walk an opaque mount
- Draft: either expose the route table on the opaque app or treat the known
  test mount as inspectable. Keep the refuse-startup default for unknown
  opaque mounts. Align with the re-export fix already on the boot-route branch.

### #4131 Unit collection ImportError
- Severity: medium (advisory until 2026-10-24)
- Draft: pin the missing import or skip the collection with an explicit
  marker. Do not leave a bare collection error on the unit lane.

### #4104 Regression gates unenforced
- Severity: Sev1
- Root: ace886be archived ci.yml; Frontend, Backend Test, GameForge, Cockpit
  Smoke no longer run
- Draft: restore the four lanes as required checks on main, or document the
  replacement workflow and update branch protection. Until then, treat main
  merges as unguarded for those surfaces.

### #3902 Legacy runs return HTTP 409
- Severity: low
- Draft: cancel with the force flag or ignore 409 on already-completed runs.
  Do not block the cleanup job on a 409.

### #3791 Retire 82 ancestor refs
- Severity: medium
- Draft: verify each ref is an ancestor of main, then delete. Keep a ledger
  of deleted SHAs. Do not delete any ref that is not a proven ancestor.

### #3790 Learning-evidence seam #1749
- Severity: medium
- Draft: re-run the closed seam tests against current main. If green, close.
  If red, open a follow-up with the failing assertion.

### #3787 E2E campaign readiness
- Severity: medium
- Draft: confirm logging, parse, isolation, and gap custody contracts exist
  and are referenced by the campaign runner. No new runner until those four
  are green.

### #3721 AI repository atlas
- Severity: medium
- Draft: generate the atlas from the existing capability and file-tree
  registries. Do not hand-maintain a second inventory.

### #2464 UI token consolidation
- Severity: low
- Draft: single token module under frontend/theme. Deprecate parallel
  sources. Ship behind the existing theme flag.

### #2457 Dependabot yarn.lock
- Severity: high (security)
- Draft: bump the transitive alerts that have patches. Pin the rest with
  an expiry. Do not ignore high alerts without a ticket.

### #2023 Night + Idle Plan
- Severity: low
- Draft: confirm the plan document matches the current scheduler. Update
  or close.

## Drafts

- #4153 MERGEABLE — review and mark ready if checks clear
- #4152 MERGEABLE CLEAN — ready for review
- #4127 GitHub still reports dirty; local merge-tree was clean. Re-check
  after the next main push or split the PR if the diff stays over 300 files.
