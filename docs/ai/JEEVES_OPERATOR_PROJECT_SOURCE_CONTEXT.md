# Jeeves — verified project source context for original local edits

Jeeves now has a **real source-grounded edit path**. Previously, the offline
source-repair agent could generate original new files but had to ask the
operator to hand-supply the full expected original SHA-256 for any edit.
If a human did not provide an exact hash, the local GGUF could invent one,
making its edit proposal unverifiable.

This feature adds independent **read-only source selection and snapshot
review** before model generation. The user chooses a tiny, explicit set of
project files; the desktop reads their exact original UTF-8 and SHA-256
with the already-existing descriptor-rooted project source guard, then
provides that source as **untrusted task data** to the same installed
GGUF. The model gains no filesystem tool, Git tool, network permission
or automatic ability to write files.

## What is working

1. Open the existing **Generate source with bounded repair** desktop UI.
2. Select the trusted original project root. Choose `existing-edits` as
   the original output schema.
3. Enter **one to four project-relative existing file paths**, one per
   line, in the new source-path selection box. Use exact file names;
   globbing, arbitrary directory search, relative `..` traversal,
   symlinks and secret/credential paths are not allowed.
4. Select **Review original SHA + full text**. The app opens each
   explicitly named source file with `O_NOFOLLOW` beneath the pinned
   original project root and checks regular file type, inode, owner,
   hardlink count, writable mode, length and UTF-8 bytes.
5. A separate window shows **all original source text and full SHA-256**
   so the operator can verify what will be sent to their privately
   installed GGUF. The manifest SHA-256 covers every exact original
   path, content, byte count, inode, ctime, mtime and project root
   identity. Source contents do not appear in public receipts.
6. Explicitly approve the original finite native model work. The
   previously existing single GGUF/SQLite worker is used, not a second
   provider or agent. Up to three independent repair turns may run.
7. Before **each** native turn, the runner checks every selected
   original file by the same pinned descriptor guard and compares
   exact bytes, SHA-256, inode/mtime/ctime/mode and original root
   identity. It checks the source once more after a returned native
   turn, before accepting its committed SQLite result.
8. The exact source is included in a structured JSON task-data
   section along with **the independently computed original SHA-256
   for each path**. The model is instructed to use only those hashes
   when proposing existing-file edits. No forged source digest can
   satisfy the subsequent real descriptor check.
9. The original source repair workflow accepts only a committed
   response with the correct request ID, installed model identity,
   SQLite session, answer SHA-256 and no-replay proof. It then
   verifies the proposed edits against real unchanged original files,
   parses supported source syntax and produces a completely separate
   reviewable Git patch. Human patch approval is **still mandatory**.
10. If any source file changes, is replaced or becomes unsafe before
    or during a native turn, the operation **holds immediately**.
    The native effect might have committed; it is not repeated
    automatically. Review fresh source and allocate a NEW work order
    before trying again.

## Finite resource and trust envelope

Source selection is limited to **four** exact files, **6 KiB per file**
and **8 KiB aggregated**. Original file paths are limited to 1,024
bytes as a selection list, and the rendered JSON context is limited
to 11 KiB. The already-enforced GGUF prompt limit remains **32 KiB**,
including the human task, context and any repair diagnostics.
The native source generation remains limited to one–three independent
SQLite-committed model turns and 16 KiB per generated proposal.

The selected files must have supported source extensions and
ordinary names. Hidden/control directories and names containing
credential indicators (such as `secret`, `api_key`, `password`
or `id_rsa`) are refused by the existing workspace search naming
policy. The operator selects exact filenames: no recursive crawling,
`Path.resolve` through hostile ancestors, command execution or
unbounded text collection is performed.

Prompt content is JSON-escaped, labels all original source as
**reference data, not instructions**, and cannot grant new model
tools. This separates untrusted project code—including strings
which look like instructions—from the user-approved task.

## Distinguish snapshots from effects

An original source snapshot is **not** an editable authorization or a
promise the file will remain unchanged. It is an immutable
source-bound witness which must be rechecked at each privileged
boundary. The final Git patch still requires original SHA checks,
syntactic source qualification, exact diff review and an operator
entering both the source-manifest and patch SHA-256 before export.
Production never runs generated source, commits to Git, overwrites
original files or silently promotes an inert patch to release.

Source-only regression tests validate real UTF-8 hashes, full
context formatting, symlink/hardlink/credential-name holds, inode
replacement, exact source drift between model turns and the correct
SQLite request-custody witness using a synthetic native worker.
They cannot certify GGUF model quality, actual Windows 11/WSL2
laptop readiness, device pressure, GPU performance, rights to
third-party weights or final release.
