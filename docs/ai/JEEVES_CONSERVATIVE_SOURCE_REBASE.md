# Jeeves offline source reconciliation: conservative three-way review

A local-first code builder must not assume the project is frozen between
model generation and a human's approval. The desktop already revalidates
original file hashes before exporting source patches, refusing to
overwrite changed files. This feature adds a useful next step:
**non-destructive recovery of a stale reviewed patch** without silently
dropping external editor changes or trusting model-generated conflict
resolution.

## Original, local, proposed

Every existing-file patch already carries three separately evidenced
pieces of information:

- **Original (base)** — the exact UTF-8 file bytes, original
  SHA-256, pinned device/inode/mode/mtime, and trusted project root
  identity recorded at the operator's earlier review.
- **Local (current)** — new bytes freshly reread from an actual,
  no-symlink, owner-checked source descriptor when reconciliation
  is explicitly requested.
- **Proposed (Jeeves)** — the exact replacement UTF-8 text already
  bound to the reviewed model proposal and source manifest SHA-256.

The rebaser uses conservative finite line-based differences:
`base → current` captures external editor changes, and
`base → model` captures the model's original suggestion. If their
modified line intervals are disjoint, it composes both changes
without overwriting either. At an equal insertion position,
an insertion adjacent to a conflicting replacement, or any
overlapping line range, **it refuses automatic resolution**.
If both sides produced the same exact hunk, it counts it once.
A change already present in the current file creates no new work.

It never emits Git conflict markers into the project, runs Git,
restores previous originals, rewinds a checkout, stages an index,
writes a source file or asks a model to choose the winner.

## How to use in the actual desktop

1. Use **Build reviewed Git patch** and inspect your original source
   proposals and complete diff.
2. If files have changed since the review—or you suspect another
   editor updated them—choose **Reconcile original edits after
   external changes**. The app reopens the source root and every
   reviewed path with descriptor-bound identity checks.
3. For an existing file that is unchanged, the original proposed
   replacement remains a candidate. For an external, nonoverlapping
   edit, the app creates a *new* strict
   `jeeves.workspace.existing-file-edits.v1` JSON proposal with the
   **new actual current SHA-256** and the merged replacement text.
4. For still-absent new paths, it carries forward their original
   `jeeves.workspace.new-files.v1` text. If a proposed new path
   has appeared, the package is in conflict and cannot be silently
   transformed into an existing-file edit.
5. If **any** original source edit conflicts, the entire
   reconciliation returns `conflicts-held`, reporting bounded
   relative paths and hunk counts without publishing a partial
   new proposal or private source contents. Resolve explicitly
   in your normal editor/source-control workflow.
6. When all changes are independent, the desktop replaces only
   the **proposal text panes** with the rebased JSON. It invalidates
   the *entire prior review and both prior approvals*. It does
   **not** create/export a patch at this point. Re-run
   **Review COMPLETE project diff**, inspect the new full patch,
   read its syntax qualification, enter both **new** full
   SHA-256 values and separately approve the new private export.
7. If all model changes are already present, the report is
   `already-present-no-work` and no duplicate source operation
   is created.

## Strict safety limits

Reconciliation is source-only and deterministic with no external tools.
It uses the existing original workspace root, `O_NOFOLLOW` child
descriptors, exact source fingerprints and finite UTF-8 limits.
A single source is bounded to **2,048 lines** and **256 change hunks**
per side; the existing 64 KiB per-file and aggregate replacement
limits still apply. More complex merges are held for manual review.

The report's SHA-256 covers the old approved source/patch identities,
per-file conflict findings, and the complete proposed new JSON text.
Public receipts disclose only a source-relative path, original/current/
proposed SHA-256, hunk counts, new rebase SHA and explicit booleans
showing **no source modifications, no Git index changes and no
automatic conflict resolution**.

Conflicting edits on the same line are never silently merged, even
when they appear to change different characters in that line. This
is a conservative safety tradeoff rather than a promise of general
three-way semantic merge correctness.

This feature is not a live GGUF test, device memory qualification,
self-executing code agent, automatic Git application, source
compilation or release certification. After rebase the operator
must review the new proposal, run static syntax checks, separately
export an inert patch and eventually perform Git/CI and hardware
acceptance where appropriate.

The source test suite covers disjoint changes, exact identical
edits, same-line conflicts, insertion collisions, CRLF, no-EOL
preservation, changed file inodes/root, symlinks, new-file name
collisions, SHA tampering, no source writes and no subprocesses.
