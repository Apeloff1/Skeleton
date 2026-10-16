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


## Content-aware reconciliation before choosing a landing path

Use `scripts/audit_branch_content_coverage.py` when a historical branch appears
divergent merely because its commits were squash-merged or replayed elsewhere.
It compares **every changed path since the common ancestor** with the same path
on an immutable current-main snapshot, including Git executable modes. For
renamed files, the default no-rename mode deliberately preserves both old and
new paths for inspection. It never modifies files, refs, or issues.

```bash
# Fetch relevant remote branches first. The auditor examines only refs present
# in this particular checkout and does not claim full remote coverage.
git fetch origin main 'refs/heads/feat/adventure-systems-depth:refs/remotes/origin/feat/adventure-systems-depth'
python scripts/audit_branch_content_coverage.py \
  --main-ref refs/remotes/origin/main \
  --branch refs/remotes/origin/feat/adventure-systems-depth
python -m pytest -q tests/test_branch_content_coverage.py
```

A result of `byte_identical` means the branch's last changed file content
and mode match the same path at pinned `main`. `missing_on_main` indicates
potential work to rescue. `different_content_or_mode` requires owner review;
newer main code can legitimately differ from an obsolete version.
`removed_on_branch_present_on_main` means the historical branch removed a
path that current main still has. None of these results grants merge,
retirement, or deletion approval. In particular, do **not** merge a historical
branch solely because Git says it is ahead.

The auditor rechecks the starting main and branch refs after inspecting their
pinned commit objects, and aborts if either moves. The historical
`feat/adventure-systems-depth`, `feat/design-bible-asset-depth`, and
`feat/production-planning-depth` module blobs were separately observed
byte-identical on GitHub current main on 2026-10-16 despite divergent
ancestry counts. This observation is narrow: it does not establish complete
equivalence of those branches, all repository refs, or their documentation.
