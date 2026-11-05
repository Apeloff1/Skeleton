# Jeeves — cold verified native source into a private project artifact

Jeeves now has a continuous, entirely local original-code handoff
that does **not** require copying generated source through a shell:

1. **Inspect** and SHA-bind the operator's original source-building
   task, model/resource settings and selected original files;
2. **Generate** original source with the independently installed
   GGUF and the canonical principal-bound SQLite chat;
3. **Save** the validated native proposal to an owner-private
   `*.source.json` file, with no source code in stdout;
4. **Cold review** the stored bytes, current original project
   and Python cross-file import graph without starting a model;
5. **Separately approve** both full source-manifest and Git patch
   SHA-256 values; then write a brand-new private source
   overlay or an inert Git patch, not the original project.

This new headless delivery layer closes the final manual JSON
copy/paste gap between the already existing private-native
escrow and offline source/patch review workflows. It does
not add another provider, cloud tool, shell, background daemon,
hidden memory store or generated-code execution environment.

## Original private-source review command

After saving a native source proposal through
`desktop_native_proposal_cli`, take its public
`private_file_sha256`, `private_file_bytes` and original
`job_sha256`. Construct this strict one-object request
in an owner-private file:

```json
{
  "schema": "jeeves.workspace.native-escrow-delivery-cli.v1",
  "action": "review",
  "project_root": "/private/source-project",
  "saved_proposal_file": "/private/source-escrow/original.source.json",
  "expected_saved_file_sha256": "<full saved file SHA-256>",
  "expected_saved_file_bytes": 5248,
  "expected_job_sha256": "<full original task/job SHA-256>",
  "target": null,
  "source_manifest_sha256": null,
  "source_patch_sha256": null
}
```

Use the actual complete original values; placeholders above
are not acceptable input.

```bash
python -m skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_native_source_delivery_cli \
  < /private/source-escrow/review-original.json
```

The review step is strictly **read only**. The private
source file is opened under a pinned descriptor,
with `O_NOFOLLOW`, exact size, owner, mode, link count,
inode, mtime and full SHA-256 checks. Its JSON is parsed
with strict duplicate-key/nonfinite rejection, canonical
serialization, original task/model/SQLite source identity,
complete source and patch digests and private code digest.

**Never** trust the saved model's source assertions alone.
The verifier uses the independent original project-source
reader to reopen all actual existing files, check full
original SHA-256 and inode/mtime, and prove all proposed
new paths are still absent. The entire mixed source
plan is regenerated as a deterministic Git-compatible
patch, with supported Python/JSON/TOML parsed without
execution and the Python import graph recomputed.

Any changed original file, replaced private escrow,
symlink/hardlink/unsafe mode, unsupported syntax,
impossible relative import, full manifest/patch SHA
mismatch or unexpected source path is held.

The response lists all exact changed paths, original
and replacement SHA-256 values, code language status,
model/job identity and source/patch/graph digests.
It contains **no original or generated source text**
and no owner-private absolute project paths.

## Explicit private source staging

If the human has independently inspected the private
source proposal and its complete intended changes,
prepare another request by changing:

- `action` to `stage`;
- `target` to a **new** stage folder path in an
  already existing, owner-private `0700` directory
  outside the original project;
- `source_manifest_sha256` to the full reviewed
  original source-manifest SHA from the read-only result;
- `source_patch_sha256` to the full reviewed patch SHA.

Then run:

```bash
python -m skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_native_source_delivery_cli \
  --approve-private-stage < /private/source-escrow/approved-stage.json
```

Both full digests and a separate CLI flag are required.
The action reopens the original private source file and
actual source project again, then calls the already
qualified `stage_reviewed_overlay` original implementation.

It writes the **actual complete replacement source
bytes** for each new and existing file into a brand-new
`0700` owner-private source overlay with `0600`
contents, canonical exact SHA metadata and a
last-written completion seal. It never overwrites
an existing stage, changes the original checkout,
runs the generated code, writes Git index or executes
a model.

The stage is a **partial changed-file overlay**,
not an automatically runnable full repository.
Independent compiler tests and project dependencies
are still necessary before treating that code as
working software.

## Separately approved inert Git patch

To export exactly the same reviewed source as a
Git-compatible patch rather than final files,
use `action: "export-patch"` with a new
`/private/patches/reviewed.patch` output name
outside the original tree, the same full original
source-manifest and patch SHA values, and:

```bash
python -m skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_native_source_delivery_cli \
  --approve-private-patch < /private/source-escrow/approved-patch.json
```

This calls the previously built, separately audited
`export_reviewed_patch` with all original
descriptor, syntax, content-hash, no-clobber
and owner-private publication checks intact.

The patch is inert source data. The product does not
run `git apply`, `git add`, `git commit`, push,
merge or launch the code. Actual Git changes remain
a separate explicit human review and repository
CI/security workflow.

## Independent permission and failure boundaries

The model never chooses the save, stage or patch
location and receives no new filesystem tool.
The human provides the saved private-source file
and expected SHA directly, and approves ONE
separate private output with ONE dedicated CLI flag.
The CLI rejects the wrong action flag, hidden JSON
fields, bool/integer confusion, duplicate/nonfinite
JSON, unsafe paths and missing exact SHA identities.

No model/SQLite process is started in this delivery
command, even during cold verification. Therefore
a failed private stage or Git-patch export cannot
cause a repeat of any previously committed model
inference. The original native SQLite session and
saved source file remain independent, read-only
evidence.

A failure after a private stage starts can leave an
**unsealed partial owner-private directory**.
Such a directory cannot pass the cold stage
verification and is never silently treated as
completed work. No unrelated source or Git files
are automatically removed.

Existing resource ceilings apply: no more than
24 changed source paths, finite original source
file sizes, a 16 KiB native generated proposal,
32 KiB canonical private model-source record,
768 KiB inert Git patch and 1 MiB private
final-source overlay. The application cannot
turn these into millions of unreviewed file writes
in one tool call; large ecosystems are built as
separate explicitly reviewed work packages.

## Source testing and device/release holds

The source-only tests exercise actual private
files and a real disposable project tree with
new-source and original-file edit in **the same**
saved native proposal. They check the real
private-stage file contents and completion seal,
inert Git patch byte hash, unchanged originals,
cross-file Python imports, cold ownership/hash
rechecks, stale originals, new-path collisions,
tampered or linked private source files,
approval denial, stdout redaction and lack of
model/Git subprocess execution.

The fake upstream native receipt is a test
fixture only. This does **not** qualify an
actual GGUF model run, real Windows 11/WSL2
hardware, model licensing, GPU/device pressure,
unexecuted generated source or a full consumer
release. Existing exact-head security/CI checks
and device acceptance remain separate holds.
