# Jeeves desktop — complete reviewed Git patch packages

The offline Jeeves desktop now has a single source-delivery workflow for
**new files and verified changes to existing files together**. This closes
a practical gap between the local GGUF's original source proposals and a
reviewable portable change set.

The feature is intentionally **human-gated and inert**: the model returns
proposed source *data*. It is never given a shell, Git credentials, arbitrary
filesystem access, repository write grants, an auto-merge capability or
permission to execute generated code. The operator can export a real,
Git-compatible patch, but must separately decide whether and where to apply it.

## Original input formats

The desktop already supports these independent strict JSON formats:

- `jeeves.workspace.new-files.v1` — relative new filenames and full
  UTF-8 text content. An existing destination is always refused.
- `jeeves.workspace.existing-file-edits.v1` — relative existing
  filenames, their expected full original SHA-256, and full proposed
  replacement text. The original file must still match the expected
  digest when the proposal is inspected.

**Build reviewed Git patch** accepts either kind alone or both. It parses
each with the existing canonical desktop workspace verifier. The project
root is selected by the operator, not inferred from model text. The two
source plans must describe the exact same pinned root inode/device.

The combined source bundle is bounded to **24 files**, and the rendered
unified Git patch to **768 KiB**. Each individual source file retains the
existing input bounds (up to 99 KiB for a new file; 64 KiB for an existing
source file) and an explicit no-write permission policy.

## Review-and-export sequence

1. Launch Jeeves on an independently admitted local model, or work with
   a previously saved source suggestion. Select **Build reviewed Git
   patch** from the desktop composer.
2. Choose the trusted project root and paste the strict new-file
   proposal, the existing-edit proposal, or both. The last model
   answer is initially placed in the matching source pane if its
   JSON schema can be identified; this does not approve it.
3. Click **Review COMPLETE project diff**. The desktop descriptor-reads
   real original source files with `O_NOFOLLOW`, verifies
   ownership/mode/link count/size/inode and hashes, proves new paths
   absent and rejects Git administrative/credential paths and
   duplicate case-folding filenames.
4. The source plan generates one deterministic Git-compatible
   unified patch. Each source path is represented by either a
   `diff --git a/... b/...` change or a new `100644` source
   file; none are marked executable. Both original and replacement
   full SHA-256 values and the complete original manifest digest are
   included in the review receipt.
5. Read the full actual patch in the scrollable window. The renderer
   preserves original UTF-8, CRLF line endings, text Unicode, and
   files without a final newline via Git's standard explicit
   no-newline marker.
6. Independently type **both** the complete original manifest
   SHA-256 and the generated patch-byte SHA-256 in the approval fields.
7. Choose a brand-new `*.patch` output filename inside an existing
   owner-private mode `0700` POSIX/WSL2 directory **outside
   the original project tree**. Confirm the separate export action.
8. At export time the desktop reopens the original trusted source
   descriptors, verifies the same original root inode, original
   file identities and byte digests, confirms that all new
   destinations are still absent, re-renders the same patch digest,
   and creates the private file with `O_NOFOLLOW|O_EXCL`,
   owner-private mode `0600`, full `fsync` and readback SHA-256.
   It rechecks original source again before publishing a success
   receipt. It never overwrites a previous patch.
9. **Verify saved patch** reopens the private output by a pinned
   descriptor and checks owner, mode, single link, size, unchanged
   inode and exact SHA-256, without touching source.
10. Only after independent manual review, use the Git tooling you
    already trust in an appropriate **separate checkout or branch**
    to run `git apply --check <escape><patch-file></escape>`.
    This export itself never runs `git apply` or changes Git's
    index. Applying or committing any patch requires separate
    operator authorization and normal repository checks.

## Why this is a new working capability

Previously, new-file proposals could create one source file at a time,
while changes to existing files could only create inert sibling
candidates. There was no single exact-source portable artifact to
review, validate in Git or transfer to another approved checkout.

The new combined package carries **all** selected source changes in one
Git-native object, with deterministic order and SHA-256 identities,
while still guaranteeing no live project files are overwritten during
construction or export. It is usable as an upstream input to branch
review and build/test workflows without granting the model direct
execution or commit privileges.

This is different from making the model a Git automation account:
the model still cannot issue tools to Git, publish pull requests,
apply patches or automatically change the checkout. It can produce
a complete **reviewable deliverable** that the operator may apply
after `git apply --check` and ordinary change-control review.

## Security and hold conditions

The exported patch may include **private original source context**.
Treat it as sensitive content. It is not encrypted; `0600` file
mode and `0700` owner-private directory permissions protect it from
other OS users, not from anyone already using the same OS account.
Never commit the exported private package blindly or upload it to
a public issue.

Export refuses changed originals, replaced inodes, symlinked sources,
unauthorized writable/hardlinked source files, new-path collisions,
oversized or malformed source text, new executable-mode proposals,
mismatched approval digests, shared/unsafe output directories and
existing exported filenames. It never retries after an ambiguous
I/O publication; inspect the private output independently.

The source-only regression suite checks patch bytes with actual
`git apply --check` and a disposable Git checkout. This proves
patch syntax on the test runner only, **not** a completed model
build, real native GGUF inference, physical WSL2 qualification or
the contents' correctness. Model licensing, security gates,
native cancellation and release readiness remain independent
holds.

**Root security model:** POSIX descriptor-rooted and WSL2 paths;
native Windows reparse point custody is not certified. Parent
directories and original project trees must meet the existing
source custody policies. Every output receipt explicitly states
`project_files_modified=false`, `git_index_modified=false`,
`patch_applied=false` and `release_certified=false`.

## Source structure check before private export

Every generated replacement is now checked through a non-executing
built-in parser where reliable: Python AST, strict JSON, and TOML.
Invalid supported syntax **blocks** export; other formats are
explicitly `unverified`, not falsely passed. Results are bound
to the exact reviewed replacement SHA-256 and shown in the patch UI.
The private exporter runs the gate again before creating a file.
See `docs/ai/JEEVES_STATIC_SOURCE_QUALIFICATION.md`.

## Non-destructive reconciliation after project drift

If someone edits source between review and export, the normal exporter
still refuses changed originals. You can now select **Reconcile original
edits after external changes** to produce a NEW candidate for independent
line changes, using the exact previously reviewed base and current
descriptor-read source files. Overlapping edits and new path collisions
hold the entire package. Neither source files nor Git are changed,
and all prior digest approvals are invalidated before a new review.
`docs/ai/JEEVES_CONSERVATIVE_SOURCE_REBASE.md`.

## Real native source generation and bounded repair

Jeeves can now originate a strict source proposal through the existing
installed GGUF and principal-bound SQLite conversation, not merely
process one the user pasted. The **Generate source with bounded repair**
desktop action executes at most 1–3 unique native turns, feeds only
sanitized schema/static parser diagnostics back into a distinct
SQLite-committed repair turn, and stops on uncertainty or exhausted
budget. A passing proposal must still receive **new independent human
review** before any source patch export. Details:
`docs/ai/JEEVES_NATIVE_SOURCE_SELF_REPAIR.md`.

## Privately staged final source files (no checkout writes)

In addition to one inert Git patch, the operator can now choose
**Stage reviewed SOURCE files privately** after checking both
full SHA-256 approvals. It creates a NEW owner-private `0700`
directory outside the project, containing the actual changed
`0600` UTF-8 source files, a canonical hash manifest and a
last-written completion seal. Incomplete or tampered stages
never count as qualified. The original checkout remains
unchanged, and staged files are not executed or merged.
See `docs/ai/JEEVES_PRIVATE_SOURCE_OVERLAY_STAGING.md`.

## Import-link evidence on private delivery

Approved Git patch receipts now include the SHA-256 and status
of the non-executing Python source dependency graph. The same
graph is included in sealed private source-overlay metadata.
Invalid package-relative import depths block either form of
private delivery; external dependencies remain unverified.
This does not execute generated source or change the checkout.
`docs/ai/JEEVES_OFFLINE_PYTHON_SOURCE_GRAPH.md`.
