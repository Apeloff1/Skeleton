# Jeeves offline source qualification: parser-verified vs unverified files

The local GGUF can author source files, but *looking plausible* is not enough
to claim that they parse. The desktop now performs a deterministic,
**non-executing** source qualification on a complete reviewed Git patch
before any private export can be approved.

This is the next operational layer after
`docs/ai/JEEVES_PORTABLE_GIT_PATCH_DELIVERY.md`. It strengthens the
local-first code builder without giving the model a shell, IDE automation,
Git credentials, arbitrary file write permissions or another provider.

## What is checked

The full source plan and exact replacement UTF-8 bytes are already bound to
original Git patch SHA-256 plus an operator-approved full manifest SHA-256.

The new structural gate parses each exact replacement file, records its
original relative path and SHA, and returns one of three explicit states:

- **`parse-clean`**: the file parses with the locally supported *syntactic*
  parser. This is not a compile, package import, type check, build or
  executed runtime test.
- **`syntax-held`**: a supported source file is syntactically invalid,
  exceeds the finite structural budget or failed a parser. The GUI
  disables patch export; the source must be fixed and re-reviewed.
- **`unverified`**: there is no sufficiently reliable local no-execution
  parser in this deployment for that extension. The file may still be
  exported as **inert** patch data, but its parser status cannot be
  silently upgraded to `parse-clean`.

Supported parsers are Python source `*.py` and stub `*.pyi` using
the standard library `ast.parse`, canonical JSON `*.json`
using strict stdlib `json.loads` with duplicate-key and
nonfinite-number rejection, and TOML `*.toml` using Python's
`tomllib`. Each language's parser validates structure only;
a valid import statement or `def` does not mean its target exists
or that generated code will execute safely.

Other extensions accepted by the original source-authoring boundary,
such as TS/JS, Rust, Go, Markdown, YAML, SQL, Java, C/C++, HTML,
CSS and shell scripts, are explicitly marked **unverified**. The
application never claims those languages have been compiled or parsed
without first supplying a credible parser and exact matching checks.

## Security and resource limits

- Maximum of **24** previously reviewed source entries and **768 KiB**
  of combined replacement UTF-8 bytes. The existing patch/source size
  ceilings still apply independently.
- The Python AST walk is capped at **50,000 syntax nodes** per file
  and **4,096** top-level function/class definitions. Deep recursive
  constructs or parser memory failures are held.
- A finite 10-second overall budget is observed between files.
  It is not a hard process-level preemptive CPU timer; actual sandboxed
  language compiler execution remains a separate unqualified capability.
- Every diagnostic is bound to the exact replacement SHA-256 and
  reports only a source-relative path, finite line/column and a
  controlled error code. It never includes `SyntaxError.msg`, full
  source code, access tokens, private absolute paths or file contents.
- All new source parser work happens in the app's trusted Python
  process but through parsing APIs only. It does not import, compile,
  execute, evaluate or dynamically resolve generated source text.
- Git remains completely inactive in production. No original project
  file, Git index, native SQLite history or model artifact is changed.

## Offline desktop workflow

1. Select **Build reviewed Git patch** and provide the original
   new-file and/or existing-file proposal.
2. Click **Review COMPLETE project diff**. The app verifies original
   file descriptors/hashes and constructs the exact inert Git patch.
3. It then parses every supported generated replacement, producing
   a **structural** status and counts of clean, unverified and held files.
   The full review includes the source manifest and patch SHA-256.
4. A generated Python, JSON or TOML syntax error blocks the export
   button, with a finite source-relative issue code/line for repair.
   Change the original proposal and run the review again.
5. An otherwise valid source patch containing e.g. TypeScript is
   explicitly marked `mixed-unverified`. The operator may still
   export the patch but knows that the TS compiler has **not** run.
6. Type both reviewed digests, select the owner-private destination
   and approve the new no-overwrite source package. The **actual
   private exporter re-runs qualification**, independent of the UI's
   earlier status. It refuses newly malformed supported files.
7. Run `git apply --check` and the required language-specific
   compiler/type/lint/tests separately in your approved checkout,
   then have the operator authorize application, CI and any release.
   Never mistake parser pass for an actual executable product.

The export receipt includes `static_source_status`,
`parse_clean_count`, `unverified_source_count` and
`source_code_executed=false`. The generated source content remains
private. Neither source parsing nor exporting changes a real project
checkout.

## How this moves the baseline

The desktop now supports an end-to-end **original idea → local GGUF
source proposal → original file identity/patch review → static
syntactic analysis → private Git-compatible patch artifact**
workflow. Human-controlled Git application, actual compilers and
unit/E2E runs are still distinct. The agent cannot promote a
parser result into device/model or product-release certification.

These source-only regression tests cover valid and invalid Python,
duplicate-key/nonfinite JSON, malformed TOML, unverified TypeScript,
exact original SHA-256 bound reports, no code execution and prevention
of private patch export when a supported parser rejects the source.
This is not evidence of physical Windows 11/WSL2 hardware, legal
model rights, real GGUF inference, device pressure or final required
release checks.

## Project-relative Python source graph

Source review also produces a **SHA-bound Python AST import
graph** for Python modules included in the same exact original
Git patch. It distinguishes links between reviewed sources from
unverified external/original project imports, reports observed
cycles, and blocks impossible package-relative import depths
before private patch export. It does **not** import or execute
the proposed code or assert external dependencies exist.
See `docs/ai/JEEVES_OFFLINE_PYTHON_SOURCE_GRAPH.md`.
