# Jeeves — private source overlay staging for complete reviewed changes

The local-first Jeeves coding workbench now goes beyond exporting inert
Git patch text. It can write the **actual replacement source files** from
a previously reviewed proposal into a brand-new, owner-private staging
directory that is entirely separate from the original project.

This is a safe bridge from model-authored work to something an operator
can open and inspect directly. It is **not** an authorization for the
model to overwrite original project code, run tools, modify Git, or
implicitly execute the generated source.

## Why this exists

A Git patch is a good, portable review format, but it does not display
what the finished new and modified source files look like in a directory.
Jeeves already supports:

- exact original-source selection with independent SHA-256 verification;
- one SQLite-bound model generation containing both new and existing
  source file proposals;
- strict new-file, existing-edit, original path and original inode checks;
- non-executing Python/JSON/TOML syntax qualification;
- full deterministic Git patch, manifest and patch SHA-256 review.

The new private source overlay takes the **same complete reviewed
PortablePatchPlan** and writes each final replacement as a normal
`0600` text file underneath a fresh `0700` private directory.
Existing-file changes and genuinely new files are both represented
by their **final replacement contents**, not diff hunks.

## Desktop workflow

1. In the main Jeeves desktop, choose **Build reviewed Git patch** or
   use **Open COMPLETE operator patch review** after an original
   SQLite-committed native source-generation task.
2. Select the trusted original source root and review one or both
   proposal panes, then choose **Review COMPLETE project diff**.
3. Review the **entire** resulting Git patch and verify the displayed
   per-file original/replacement SHA-256 plus the complete original
   manifest SHA-256 and patch SHA-256.
4. Enter **both full 64-character digests** into the review UI.
5. Choose **Stage reviewed SOURCE files privately**. Select a
   **pre-existing**, owner-private mode `0700` parent folder that
   is **outside the original project tree**.
6. Enter a **new** simple stage-directory name. An existing stage
   destination is never overwritten, merged into or reused. Confirm
   the separate operation and read its privacy warning.
7. The desktop independently re-runs the supported-language static
   source qualification and original source descriptor/byte checks.
   It refuses invalid generated Python, JSON or TOML, stale original
   files, changed original inodes or new path collisions.
8. It creates the brand-new private stage with `0700` and
   writes each actual replacement under `changes/<relative-path>`
   at `0600`. Every intermediate directory is descriptor-anchored,
   `O_NOFOLLOW` and `0700`; each file is created with `O_EXCL`,
   never made executable, flushed and reopened for byte/hash inspection.
9. `manifest.json` records each file's relative path, kind
   (`new` or `edit`), original/replacement SHA-256, byte length,
   full reviewed original-manifest SHA, reviewed patch SHA and the
   exact syntax-qualification status. It **does not** include
   project absolute paths, original full source text or secrets
   beyond any text in the proposed output files themselves.
10. Source files are checked **again** immediately before
    completion, then `seal.json` is written **LAST**. If the
    operation fails or the process dies before the seal is written,
    a partial directory may remain but cannot be mistaken for
    a completed stage by the verifier.
11. **Reverify private staged sources** reopens the directory by
    its pinned descriptor, checks exact manifest and seal bytes,
    verifies every expected replacement file SHA-256/mode/link-count,
    and rejects unlisted files, untrusted directories, symlinks,
    hardlinks, modified files and mismatched full original
    approval hashes.
12. Inspect the staged source files through ordinary trusted tools
    as the private operator. No runtime test or Git application
    happens automatically. A complete stage is a **partial project
    source overlay only**, not a verified standalone checkout
    or proof that every import, dependency or game system works.

## Security boundaries and finite budgets

The stage is limited to 24 source files and **1 MiB total final
replacement source bytes**. It uses the existing strict source
extension/path policy, the complete original source plan and
final patch SHA-256. Its metadata is limited to 16 KiB and
includes no source text. The already-separated Git patch remains
bounded to 768 KiB. The mixed native GGUF response is now capped
at the same **16 KiB** limit in both the source-repair runner and
the strict mixed-work JSON parser, repairing their previous
mismatched admission behavior.

A stage does **not** include unchanged project files. The model
cannot claim that every imported module exists, that generated code
is safe to run, or that an entire project is complete merely because
the staged files match their hashes.

The new overlay is the only new write surface: a separate
explicitly selected owner-private directory, **not** the
original workspace and not a Git repository. The original
source project remains read-only. The model cannot select
the output location or call the staging action. The operator
must explicitly approve the full SHA-256 identities and the
new private destination.

Every private output is inert UTF-8 source data. A `.sh`,
`.py`, `.js` or `.ps1` staged file remains mode `0600`;
it is never executed by staging. No `chmod +x`, package
installation, shell tool, Git branch write, network request,
auto-build, source overwrite or deployment is performed.

A failed stage **may leave a partial private folder**.
This is deliberate: cleanup that follows paths through a
noncooperating process can be unsafe. The application
does not blindly recursively delete partial results.
Only the immutable seal and exact expected hashes
authorize a *completed-preview* receipt. The private
operator can inspect/delete a partial stage separately.

## Qualification and release holds

The source-only regression suite verifies the staged source
bytes in a temporary private directory, preserved original
checkout, exact hashes, canonical manifest and seal,
cold reopen, new-directory exclusivity, original drift,
new-path collision, invalid source syntax, unsupported
payloads, tampered source, extra files, symlink/hardlink,
relaxed modes and interrupted writes.

The qualification does not itself prove real GGUF inference
quality, physical Windows 11/WSL2 device operation, GPU
pressure, correct third-party licensing, whole-project
builds or final release. Such evidence and all required
security gates remain separate prerequisites.

The required target filesystem is POSIX/WSL2 with
supported descriptor-anchored `O_NOFOLLOW` operations.
Native Windows reparse-point custody is not certified.

**Status fields are intentionally narrow:** complete and
SHA-verified source overlay, `original_checkout_modified=false`,
`git_index_modified=false`, `source_code_executed=false`,
`model_source_write_authorized=false`, and
`release_certified=false`.

## Headless offline use

The same reviewed source staging and cold inspection operations
are now available through a non-inference, no-Git, strict JSON
stdin CLI. Both original 64-character SHA-256 values and an
explicit separate flag are needed for any new private write;
read-only verification does not start a model. See
`docs/ai/JEEVES_HEADLESS_LOCAL_SOURCE_WORK_CLI.md`.

## SHA-bound Python import graph in the sealed stage

The `manifest.json` and final private overlay receipt now
also preserve the exact Python static dependency graph SHA-256,
known reviewed-source import count, unverified original/external
import count and observed cycle count. The parser refuses
unqualified source graphs or provably impossible relative imports
before staging. A later cold reopen verifies that this graph
receipt is still **sealed and unchanged**; it does not claim
to have re-parsed every module or scanned the live project.
See `docs/ai/JEEVES_OFFLINE_PYTHON_SOURCE_GRAPH.md`.
