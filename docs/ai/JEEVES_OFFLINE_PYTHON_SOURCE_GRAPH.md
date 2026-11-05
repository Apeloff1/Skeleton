# Jeeves — SHA-bound offline Python project-link analysis

Jeeves can now inspect **relationships between multiple model-authored
Python files** before exporting a private source patch or preview overlay.

Previously the source reviewer used `ast.parse` for each generated
Python file individually, proving the syntax of one module but not
recording how that file relates to the other files in the exact same
reviewed project change. For a mixed source proposal that adds an
implementation and updates an existing entry point, understanding
those imports helps verify whether the submitted output is a coherent
source package.

The new graph is **static only**. No Python import is executed,
no `compile` or `exec` is called, no source directory is
recursively scanned, no network or dependency manager runs, and
no generated code receives a Git or filesystem write tool.

## Complete review identity

The input is the **same exact verified `PortablePatchPlan`**
that the existing Jeeves desktop already uses for a mixed
new-file and existing-file change. It contains at most 24
ordered, SHA-256-bound source changes.

Each source that ends in `.py` or `.pyi` is parsed
to a read-only AST, assigned a project-relative dotted Python
module name, and bound to its exact replacement SHA-256.
A type stub next to its `.py` implementation is a
legitimate module pair: both are parsed and hashed, while
the implementation is used for the import edge.

Each syntactic import becomes a finite record with:

- a source-relative original file path and replacement SHA-256;
- a SHA-256 for the **requested import name**, rather than
  exposing the literal imported package name in public receipts;
- a source-relative target path **only if** that target is one
  of the exact files independently included in the reviewed patch;
- a line number, relative import depth and explicit status.

The result has its own deterministic `graph_sha256`
derived from the complete source manifest, patch SHA-256,
source-file graph and observed cycles. Changing one
generated source file changes its original project
manifest/patch identities and therefore the graph digest.

## Three distinct link results

**`linked-reviewed-source`** means an import resolved
to another Python source file included in the exact original
reviewed change. It does not mean that the imported
module will successfully initialize or that a function
it exports is semantically correct.

**`unverified-original-or-external`** means the imported
module was not among the submitted changed files. This
includes standard-library packages, installed external
dependencies, and existing unmodified project files.
Jeeves does **not** assume any of those modules exist,
have the right version, or are safe to execute. It
labels them explicitly *unverified*, rather than
fabricating a complete dependency pass.

**`invalid-relative-import`** means the generated
source uses a relative import depth that is impossible
from the path's own package hierarchy, such as
`from ...module import value` from a
first-level package module. Python AST parsing alone
may accept this syntax, but the package-relative depth
is provably invalid. The source review reports
`invalid-relative-held` and **refuses private
patch export and source-overlay staging**. The
native GGUF repair loop can receive only a finite,
sanitized `invalid-python-relative-import`
diagnostic and use another explicitly bounded SQLite
model turn. It never silently edits code or repeats
an uncertain turn.

## Observed cycles are not runtime claims

The graph records observed import cycles **only among
reviewed changed files**. Cycles are shown to the
operator as a possible design problem, not treated
as proof of a runtime failure. Normal Python import
semantics, initialization order and the behavior of
external packages must still be tested separately.

The output explicitly includes
`whole_original_project_scanned=false`,
`all_dependencies_resolved=false`,
`source_code_executed=false`,
`python_imports_executed=false`,
`python_compiler_executed=false` and
`release_certified=false`.

## Where it appears

In the desktop, choose **Build reviewed Git patch**
and **Review COMPLETE project diff**. The full review
now shows the graph status, number of known
cross-file links, number of unverified imports,
number of impossible relative imports, observed
cycles and complete graph SHA-256.

The private export and staging buttons remain
disabled when Python AST/import-graph admission
has a definitive error. The private output
functions also rerun this check independently
at the final authorization boundary; a stale
GUI preview is never enough.

The headless source-work CLI includes the graph
receipt alongside the existing source-manifest,
patch, syntax and private-stage receipts.
A read-only `review` action can show graph
issues even when the operator has not authorized
writing any private output. The native source-repair
runner can return short issue codes for invalid
relative package use, allowing a new finite
committed original request to repair the source.

## Limits and qualification

The graph is restricted to a maximum of 24
selected Python files, 256 import records per
file, 1,024 import records in aggregate and
50,000 AST nodes per file. It never walks
the entire user's project tree or loads
a provider-dependent runtime dependency graph.

The same original source approval rules,
model source and license evidence, SQLite
turn identity, capacity guards and full
Git patch private-delivery controls remain
intact. There are no new model tools,
background execution, branch writes or
file-overwrite permissions.

Source-only regression tests cover internal
links, relative import depths, a legitimate
`.py`/`.pyi` implementation and type
stub, ambiguous package paths, observed cycles,
unverified stdlib/third-party imports,
changed source hashes, source code that would
have side effects if imported, invalid syntax
and absence of any Python execution.

These tests do **not** certify physical Windows
11/WSL2 GGUF operation, installed model rights,
GPU pressure, external dependencies or full
project execution. Exact-head security/release
gates remain prerequisites before release.
