# Pinned branch-retirement custody — read-only census

Issue #3791's October 14 ledger counted **853 historical refs**; the newer
October 16 GitHub branch search returned **118 refs** including `main`.
These numbers are separate historical observations, not proof that 735 refs
were safely retired. The tool in this change does not delete anything.

## Reproducible audit

Run from a complete checkout with local branch refs populated from the desired
source, after authenticating GitHub branch metadata. A local `git clone` may
have only one checkout branch and therefore cannot be represented as an
exhaustive GitHub remote-ref census.

```bash
MAIN_SHA=$(git rev-parse refs/heads/main)
NOW=$(date +%s)
python scripts/audit_branch_retirement.py \
  --expected-main "$MAIN_SHA" --as-of "$NOW" --age-days 30 \
  --output /tmp/skeleton-branch-census.json
python -m pytest -q skeleton/testing/test_branch_retirement_audit.py
```

The report includes **every local branch**, exact tip SHA, commit age, Git
ahead/behind vs the captured `main` SHA, protected-name classification and
candidate reason. It refuses a stale main SHA, moved refs during sampling,
missing local main, malformed metadata, future commit time and over-budget
inventory. `deletion_authorized` is false for every branch, including
ancestral tips.

## A candidate is not approval

The user-facing branch search is the inventory of the *GitHub remote*, not
necessarily the `refs/heads` visible to a local clone. Before any future
pruning, recheck actual GitHub branch names and exact tips, open PR heads,
branch rules, branch age, active owners, branch ancestry, exact blob equivalence
for squash-merged histories and archival custody. Preserve all backup and
protected branches. Use a lease-bound GitHub-side policy gate and verify
deletion results in a fresh remote census. Do not treat `ahead=0` as
permission to delete; do not delete remote branches using this report.

Related: `docs/repository/BRANCH_LANDING_PATHS_2026-10-14.md` remains the
immutable older branch landing ledger, not a live authorization.
