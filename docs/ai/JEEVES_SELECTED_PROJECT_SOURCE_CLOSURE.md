# Jeeves selected-original source closure (AST-only, fail-closed)

## What this closes

A reviewed offline native GGUF source patch can be syntactically correct while
referring to unchanged project modules that were not part of the proposed
patch. The original **patch-only** Python dependency graph intentionally
marks such references unverified; it cannot silently claim a complete project.
The next cold source stage may include selected unchanged original files,
but it also must not assume those files can actually be imported.

This change adds an **exact selected-source import closure** for the same
private source capsule. It has independent source SHA-256 provenance for:

- Every operator-selected existing, unmodified source dependency.
- Every verified proposed *new* source file.
- Every verified proposed *edit* replacement.
- Every observed literal Python `import` or `from ... import` statement
  whose target is actually inside this exact bounded selected set.

A graph edge is labeled **linked-selected-original** or
**linked-review-change** only when the referenced module resolves to a
byte-identical source file in this explicit selected capsule. Imports from
the standard library, installed third-party packages, dynamic imports or
unselected project modules remain **unverified-external-or-unselected**.
Even an observed zero-unverified-imports result is *not* a claim that all
runtime dependencies exist.

## End-to-end workflow

The existing `desktop_native_capsule_cli` remains the original
operator-approved inspect/publish pathway. No new model provider or
filesystem permission is introduced.

1. The actual installed GGUF produces the original strict proposal, bound to
   its SQLite committed job. The private GGUF escrow stores the original
   proposal in a new owner-private file.
2. Cold source inspection validates the **original** GGUF result, all exact
   model/source/job SHAs, independently verifies existing-file edit identities,
   and performs the original changed-source Python syntax/graph analysis.
3. The operator selects 1–48 unchanged project source dependencies. Each
   exact full file is read with a pinned descriptor, SHA, owner, inode,
   ctime and mtime. Symlinks and suspicious paths never enter the capsule.
4. The new selected-source closure parses **both** selected original and
   final generated source as inert AST data. It never imports modules, calls
   the model, invokes tools or executes source.
5. Inspect now reports a distinct `python_closure_sha256` bound to the
   original patch and every selected file, linked import counts, unknown
   imports and `selected_python_closure_status`. The overall capsule SHA
   also includes the closure digest.
6. The operator must still independently approve the original full capsule,
   source manifest and patch digests before a new owner-private 0700 stage
   can be published. The workbench **rechecks** the closure before writing
   any source files. No original project file is modified.
7. The last-written canonical completion seal contains the exact closure SHA
   and unknown-import count. Independent cold verification reopens the
   staged source files, **recomputes the whole AST closure from the staged
   bytes**, and compares it to the original seal. It then verifies all
   other source bytes, exact directory tree, and final seal a second time.

The Tk patch workbench's source capsule review now displays the closure
status, linked-original count, unknown count and full closure SHA. The
expensive AST review runs in the workbench's background worker; only bounded
receipt metadata crosses to the Tk event thread.

## Examples of conservative outcomes

| Selected source state | Result | Next action |
|---|---|---|
| `src/app.py` imports `src/dependency.py`, both actually selected | Linked selected original, SHA-bound | Continue separate human review |
| New file imports another new file in patch | Linked review change | Continue separate human review |
| Import references a module not selected | Unverified external or unselected | Select an actual original dependency and rerun review, if relevant |
| `from ...parent import x` exceeds the source package hierarchy | Invalid relative import, held | Correct proposal; no private publication |
| Selected original Python contains syntax errors | Held; cannot claim Python closure | Select a supported valid original file or repair independently |
| Two selected files alias a single Python module identity | Held | Remove ambiguous source selection |
| Original source bytes or SHA differ after initial inspection | Held; prior approval invalid | Start a fresh source review |
| Private stage contains modified source, missing/extra file, or changed seal | Cold verification held | Independently inspect incomplete/tampered stage; never automatic promotion |

## Invariants

The closure implementation is *pure source-data analysis*, with no
`importlib`, `subprocess`, `eval`, `exec`, Python compilation or
application of the reviewed patch. The same underlying finite source
reviewer applies. Additional AST caps are:

- At most **72 total explicit source files**, of which at most 72 are Python.
- Aggregate selected plus replacement bytes at most **1,572,864**.
- At most **50,000 AST nodes per Python file** and **120,000 aggregate**.
- At most **256 imports per file** and **2,048 across selected Python**.
- Canonical owner-private completion seal at most **16,384 bytes**.
- The source dependency graph contains SHA-bound hashes, edge kinds,
  unresolved counts and observed cycles; imported names are emitted only
  as SHA digests, not unbounded strings or original source contents.

Source validation does not automatically install, run or trust code. The
module does not promise the selected capsule is a full source checkout,
self-contained executable package, running native inference, integrated
Windows/WSL2 app, successful real-device qualification or release artifact.

## Qualification

`python -m unittest discover -s skeleton/testing
-p 'test_jeeves_desktop_capsule_source_closure.py' -v`

`python -m unittest discover -s skeleton/testing
-p 'test_jeeves_desktop_private_capsule*.py' -v`

`python -m compileall -q
skeleton/ai/runtime/operational_ai/laptop_runtime`

The canonical Jeeves source-only GitHub Actions workflow also includes
these tests under its existing `test_jeeves_desktop_*.py` pattern. Only
successful **exact-head** CI execution proves they passed; the source
qualification does not itself prove real GGUF, model quality, GPU/CPU/device
pressure, native cancellation, security release or laptop installation.
