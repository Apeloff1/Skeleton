# Git Atlas — exhaustive tracked-file inventory (v1)

This read-only tooling augments the existing canonical repository-machine
atlas; it does **not** replace machine/architecture.json or declare new
feature/runtime owners.

## Run

    python scripts/build_git_atlas.py --root . --output .machine/git-atlas --revision HEAD
    python scripts/build_git_atlas_near.py --root . --atlas .machine/git-atlas --output .machine/git-atlas
    python scripts/query_git_atlas.py --root . --atlas .machine/git-atlas --query "Jeeves game editor" --budget-bytes 5000
    python -m unittest discover -s tests -p 'test_git_atlas*.py' -v

The scanner uses NUL-separated git ls-tree --full-tree -r -z -l at one
resolved commit. It does not use the bounded working-tree traversal from
RepositoryModelBuilder and therefore does not silently stop at 50,000
files. It includes snapshots, submodules (gitlinks), symlinks, binary files,
and paths ignored by the developer-oriented context scanner.

## Outputs

| Artifact | Purpose |
| --- | --- |
| summary.json | Exact commit, counts, zones, languages, mode/size coverage, digest receipts |
| files.jsonl | One sorted record per tracked Git entry: SHA, mode, size, owner, zone, feature |
| exact-duplicates.jsonl | All repeated Git blob hashes; snapshot prevalence; review-only disposition |
| navigation.json | Compact per-feature summaries, representative paths and lexical token routing |
| normalized-duplicates.jsonl | Python AST-equivalent but byte-different code candidates (nightly/manual) |
| near-candidates.jsonl | Bounded SimHash and token-Jaccard similarity candidates (nightly/manual) |
| near-summary.json | Similarity coverage, overflow limits, skips and evidence digests (nightly/manual) |

All artifacts are generated under .machine/git-atlas/ during workflow runs,
uploaded as an Actions artifact and are **not committed back into main**. The
workflow triggers on changes to main, relevant PR changes, manual dispatch,
and a daily reconciliation schedule. The expensive normalized/near audit runs
nightly and on manual dispatch, not on every PR.

Classification is first-match by .machine/repository.toml. Existing
machine/ai_file_tree.json mappings take priority for feature IDs.
Fallback feature groups are navigational labels, not authoritative capability
contracts. Unknown zones remain visibly unclassified.

## Safety and accuracy

- Blob identity is byte-level evidence. Exact copies may be purposeful
  compatibility shims, historical snapshots or empty files; **no deletion**.
- AST-normalized Python and token/SimHash candidates are now generated on
  nightly/manual sweeps. They are **review candidates, not verified behavioral
  equivalence**. Files larger than the configured bound, oversized search
  buckets, and pair limits are explicitly reported. Structural and similarity
  detection are not exhaustive proof of all possible duplicates.
- Index freshness is bound to the Git commit. Do not use the index for a
  different commit without rebuilding or explicitly verifying change impact.
- files.jsonl records Git metadata; it does not extract source symbols or
  execute files. Symbol and call indexes remain the responsibility of existing
  repository-intelligence and code-search subsystems.
- navigation.json groups paths for bounded AI context; always inspect
  source and validation evidence before applying a change.
- Check filesystem case collisions, snapshot policy, and runtime contracts
  before proposing file moves. Preserve imports, resources and test references.

## Context-budgeted Jeeves navigation

Run scripts/query_git_atlas.py with a natural-language query, max hits, and an
explicit UTF-8 output byte budget. The retrieval process loads indexes locally,
returns only a bounded group/owner/path/blob-hash projection, and fails closed
if the checkout no longer matches the index commit or its integrity receipts.
This is an **index query**, not implicit authorization to edit or move files.
Expansion into symbol-level source spans belongs to the existing code-search,
repository-intelligence and runtime permission contracts.

Generated feature shards use the existing AI-tree mapping IDs first. Other
directories receive bounded-depth navigational labels. New feature labels
do not become new canonical runtime owners.

## Follow-on milestones

1. Add incremental commit-diff reconciliation with exact-head freshness gates.
2. Broaden source-language AST parsing and independently verify near-duplicate
   behavioral equivalence (current detection is bounded and advisory).
3. Link the full inventory to existing runtime symbol, dependency, API, UI and
   test graphs; extend the new bounded metadata queries to validated source spans.
4. Produce reviewed, reversible path migration proposals. Never automatically
   consolidate files on mere hash or similarity matches.
