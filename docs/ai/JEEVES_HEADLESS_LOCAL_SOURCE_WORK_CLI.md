# Jeeves — headless offline source-work CLI

The local-first Jeeves code builder can now review, reconcile and privately
deliver its operator-approved source proposals **without starting the Tk
desktop**. This supports a laptop terminal, a user-authorized local
script or a manually invoked offline workflow while preserving the same
project source and sealed overlay safety gates.

The CLI is a **source-work utility**, not a second LLM, server,
provider, SQLite store, Git agent, automation daemon, model loader
or build system. It does not generate code itself. It accepts
source text already authored by the existing local GGUF or supplied
directly by the operator.

## Native invocation

Use the installed Python module, from the trusted checked out
Jeeves application. Its entire command interface is:

```console
python -m skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_work_cli < request.json
python -m skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_work_cli --approve-private-stage < approved-stage.json
python -m skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_work_cli --approve-private-patch < approved-patch.json
```

The request is a **single strict JSON object on standard input**.
The code reads no more than 128 KiB, rejects duplicate and nonfinite
JSON keys/values, unknown fields, unsupported actions, noncanonical
project roots and malformed/incomplete SHA-256 values. The stdout
response is another small JSON object containing only verified
source identities and evidence, never original raw source text or
private absolute root paths. Errors print a generic failure type
to stderr, not the private proposal, path or model prompt.
Every successful action still reports
`model_inference_started=false`,
`source_code_executed=false`,
`original_checkout_modified=false`,
`git_commands_executed=false` and
`release_certified=false`.

## Complete request schema

All fields are required, including `null` for unused values.
This denies hidden action parameters that might otherwise
carry unreviewed write authority.

```json
{
  "schema": "jeeves.workspace.local-source-cli.v1",
  "action": "review",
  "root": "/trusted/private/original-project",
  "new_files": "{\"schema\":\"jeeves.workspace.new-files.v1\",\"files\":[{\"path\":\"src/hello.py\",\"content\":\"def hello(): return 42\\n\"}]}",
  "existing_edits": null,
  "mixed_work": null,
  "target": null,
  "source_manifest_sha256": null,
  "patch_sha256": null,
  "patch_bytes": null
}
```

The `new_files` and `existing_edits` values must be
**JSON strings** in their already-enforced original
proposal schemas. Alternatively `mixed_work` holds one
JSON string with `jeeves.workspace.mixed-project-work.v1`.
You may supply one or both separate proposals, **or**
one mixed proposal, never both representations together.
The project root must be an operator-selected canonical
absolute path.

The `review` action rereads the real source with the
existing descriptor-rooted custody, checks all original
hashes, generates the deterministic Git patch and runs the
non-executing Python/JSON/TOML syntax gate. It emits
the **full reviewed source-manifest SHA-256** and **full
Git patch SHA-256**, as well as per-file old/new hashes,
finite source byte counts and explicit parser statuses.

If a supported syntax parser reports an error, `review`
reports a `syntax-held` source qualification. It does
not automatically execute or repair generated code.
A `stage` or `export-patch` action with such errors
is refused.

## Review, stage and export

A private write is an explicitly separate invocation.
To stage reviewed source, prepare another request with
the *same exact source proposals* and project root plus:

- `action: "stage"`;
- `target: "/trusted/private/outside-project/new-stage-name"`;
- `source_manifest_sha256` set to the **complete**
  original source SHA from the initial review;
- `patch_sha256` set to the **complete** patch SHA from
  the same reviewed source;
- `patch_bytes: null`.

Then invoke the CLI with **`--approve-private-stage`**.
Missing approval or changed/old source hashes refuse the
write. It reruns all source review and parser checks,
then creates the brand-new private source overlay directory,
writes the actual new/edited `0600` source files, canonical
manifest and last-written completion seal. The source
checkout is not modified and no code is executed.

To export a Git patch instead, use the same source proposal
plus `action: "export-patch"`,
`target: "/trusted/private/output/new-reviewed.patch"`,
both exact reviewed SHA-256 values and
**`--approve-private-patch`**. Output is an inert private
`0600` Git-compatible patch, not an applied or committed change.
No Git executable is invoked by the product.

Both actions use the same finite existing source reviewers
and no-overwrite destination policy as their Tk equivalents.
A stage or export request must be created with fresh
reviewed source and explicitly approved full digests.
The CLI never reuses a previous stage folder, appends
to existing files, retries ambiguous I/O or rewrites
the source in place.

## Read-only cold verification

A private stage can be reopened without a native GGUF or
original source proposal:

```json
{
  "schema": "jeeves.workspace.local-source-cli.v1",
  "action": "verify-stage",
  "root": "/trusted/private/original-project",
  "new_files": null,
  "existing_edits": null,
  "mixed_work": null,
  "target": "/trusted/private/outside-project/new-stage-name",
  "source_manifest_sha256": "<complete original manifest SHA-256>",
  "patch_sha256": "<complete original patch SHA-256>",
  "patch_bytes": null
}
```

It checks the sealed stage directory's owner, permissions,
file inventory, final replacement SHA-256s and canonical
manifest without touching the original project. This proves
the **staged snapshot is intact**, not that the original
project still has the same files today. No model response
is replayed during verification.

For an inert `.patch`, use `action: "verify-patch"`,
the private patch target, complete `patch_sha256`
and its exact `patch_bytes` from the export receipt.
`source_manifest_sha256` and all source proposal fields
must be `null` for that read-only verification action.

## Source-drift review

`action: "reconcile"` accepts the original proposals
but **never** a private output path, SHA approval or write
flag. It uses the existing conservative three-way source
reconciliation with current actual project bytes, reporting
a public conflict/rebase receipt only. Conflicted,
overlapping or displaced source changes remain held.
The CLI intentionally does **not** print any proposed
rebased private source text to stdout and therefore
cannot silently apply a synthesized conflict resolution.

## Limits, evidence and release holds

The CLI's source input byte bound is 128 KiB, while
the strict native mixed-work output format stays at
16 KiB, source patch remains bounded, and actual staged
files are limited to 24 changed files and 1 MiB total
replacement bytes. All outputs are checked on the
original project root, the original license/source
identity and the independent security envelope
established earlier in the desktop.

The utility is POSIX/WSL2-first. Native Windows
reparse-point handling remains unqualified.
The user must not place source proposals or private
stage contents in public Git or shared folders if they
contain confidential original code.

The source-only regression suite verifies JSON
admission, arbitrary authority denial, exact stage
and export approval, public response redaction,
mixed new/edit source, cold private stage/patch
inspection, original source drift and absence of
model/Git/OS execution. Source tests are not
real GGUF, Windows 11/WSL2 hardware, full-project
builds, security release gates or model-license proof.

## Python source dependency evidence

The read-only `review` action also includes a finite,
source-manifest/patch-SHA-bound Python AST import graph.
Links between reviewed files are shown separately from
unverified external dependencies. Provably invalid relative
import depths prevent staging or private patch export;
observed cycles are informational only. No Python imports
or generated code are executed. See
`docs/ai/JEEVES_OFFLINE_PYTHON_SOURCE_GRAPH.md`.

## Direct preceding step: real local GGUF source generation

Use `desktop_native_code_cli` to first inspect/hash an
operator-selected task, then explicitly authorize a real GGUF
and SQLite-bounded native source-generation session. It can
return an approved original proposal string for manual
review in this **separate** source-work CLI. Model-written
source is never automatically staged or applied; all actual
source and patch SHA checks here remain independent.
See `docs/ai/JEEVES_HEADLESS_NATIVE_CODE_GENERATION.md`.

## Original GGUF source to headless source-work pipeline

The native source-generation CLI can now save its
independently reviewed model proposal in a separate
owner-private `*.source.json` file without raw
code on stdout. Cold verify its task, model, SQLite,
original source and patch SHA custody, then manually
extract the original `proposal` from that private
file into this source-work CLI for a **second
independent** review and explicit patch/stage
authorization. Model-generated code is never
applied automatically. See
`docs/ai/JEEVES_NATIVE_PRIVATE_SOURCE_ESCROW.md`.

## From private native source escrow directly to reviewed deliverable

A separate `desktop_native_source_delivery_cli` now reads
an exact already-reviewed private `*.source.json` file
without any source text in stdout, independently checks
the current workspace, syntax and Python graph, and can
write a new private source-overlay or inert Git patch
after the operator explicitly approves both full source
and patch hashes plus one action-specific flag. This
avoids manually copying private GGUF code into this CLI.
See `docs/ai/JEEVES_NATIVE_ESCROW_TO_STAGE.md`.
