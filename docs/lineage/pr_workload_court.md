# PR workload court

packet: PR-COURT-20261008
parent: #80
stored_prose: 0

Classifies an already-fetched open set. Does not merge. Does not call GitHub.
Volume titles (`scatter`, `N organs`, `ERA-N`, `batch of N`) are hold-volume even if draft is cleared.
Eligible-after-ci requires a non-draft serve or token lane, base equal to the pinned main SHA, changed_files <= 12, and additions <= 2000.
A stale base is hold-stale-base. Empty windows fail closed.

Run:

```bash
PYTHONPATH=. python -m unittest tests.review_court.test_pr_workload_court -v
```
