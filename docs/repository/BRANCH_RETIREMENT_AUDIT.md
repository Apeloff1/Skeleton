# Branch retirement: evidence before deletion

The source-of-truth CLI is `scripts/audit_branch_retirement.py` (issue #3791). It is **read-only** and never deletes branches. The script reports pinned commit SHAs, exact Git tree identity, ahead/behind counts, old-enough branch candidates and protected-name exclusions.

Use an up-to-date checked-out repository, with relevant branches fetched, and record the *current main commit* rather than guessing:

```bash
git rev-parse refs/heads/main
python scripts/audit_branch_retirement.py \
  --expected-main <FULL_MAIN_SHA> --as-of <CURRENT_UNIX_SECONDS> \
  --age-days 30 --output /tmp/skeleton-branch-audit.json
python -m pytest -q skeleton/testing/test_branch_retirement_audit.py
```

A key limitation: **`scope: local_refs_heads_only`**, `remote_coverage_complete: false`. The `coverage_complete` field means the local Git `refs/heads/` listing was fully inspected and stable; it does **not** establish a complete live GitHub branch inventory. GitHub may host additional refs absent from this checkout.

The audit uses captured immutable SHA values for ancestry and tree comparisons, then rechecks branch refs. A branch can have the exact same tree as `main` yet have divergent commit history (common after squash-merging). That category is `tree_equivalent_but_divergent_history`, **not** automatic deletion approval. Protected branch names, younger refs, and divergent snapshots remain reviewed rather than removed.

Before any actual deletion, an operator must independently check current live GitHub PRs, branch protection/rulesets, expected branch-head lease, merge provenance, source owner approval, and archive/rollback custody. Historical source fragments, AI-tree overlays, masterplan volumes and intentionally mirrored paths are not garbage merely because their blobs are duplicates. **No automatic deletion is authorized by this report.**
