# Lossless exact-duplicate inventory (read-only)

This is the first bounded, full-path inventory slice of issue #3721.
It **does not** implement semantic/AST/MinHash duplicates, dependency linking,
Jeeves semantic retrieval or automatic source moves.

## Reproducible snapshot

```bash
python scripts/build_repo_exact_duplicate_atlas.py \
  --output /tmp/skeleton-exact-duplicates.json
python -m pytest -q skeleton/testing/test_repo_exact_duplicate_atlas.py
```

The script uses the already hardened `GitIndex` scanner; it rejects staged
changes before and after scanning, all unstaged changes or deleted tracked
files, git index churn or moving HEAD, and invalid identity/count/byte totals.
It reads with inherited `GIT_*` variables stripped and does **not** follow
symlinks or execute repository code. It emits every tracked path—not a
top-N listing—and exact-content clusters grouped by blob SHA, mode and byte
length. Duplicate files are still preserved as distinct tracked identities.
Cross-mode copies (executable vs text, symlink vs regular) do not collapse.

Output includes exact Git HEAD, object format, scanner source digest, full
tracked-path list, candidate clusters and explicit
`automatic_deletion_allowed: false`. It will not silently truncate; scanner
ceilings cause a failing run. Output publication is no-clobber by default;
`--overwrite` must be explicit, and no repository files or branches are
mutated.

**The report is an inventory, not a deletion plan.** Canonical/AI mirrors may
be intentionally byte-identical; imports, ownership, active runtime aliases,
licensing and release custody have to be independently verified before any
move. For safe rationalization, continue with the symbol/runtime graph, Git
history, normalized/AST duplicate analysis, semantic lenses and rollback
review requested in #3721. Pin any downstream use to the report's exact
source HEAD and source digest.
