# Jeeves — private custody for native-generated source proposals

The existing offline Jeeves GGUF can now produce validated original source
through a terminal rather than only the Tk desktop. A normal terminal
generation receipt deliberately does not include raw generated code.
Adding a flag to print code to stdout can disclose private original
project text in a terminal emulator, workflow capture, log or redirected
file. That is an unnecessary risk for an offline AI used on large
private projects.

This feature adds an independent **owner-private proposal escrow**:
an operator can explicitly authorize ONE inspected native generation
and ONE new private `0600` source file, with no proposal text
ever appearing in stdout. The output can be cold-reopened later
without reissuing inference. Human Git review and final source
staging remain entirely separate operations.

This is **not** a replacement GGUF runtime, backup model, shell,
auto-programmer, Git bot, new SQLite store or automatic patch
application. It uses the existing source-fenced
`DesktopBridge → desktop_host → SQLite NativeSourceRepairRunner`
and exact original source/patch/static graph reviewers.

## Two-phase generation and source handoff

First prepare an ordinary original task request and run its
`inspect` action using
`desktop_native_code_cli` as documented in
`docs/ai/JEEVES_HEADLESS_NATIVE_CODE_GENERATION.md`.

Read the resulting **full** original `job_sha256` and, if
existing files were selected, the exact original source
`source_context_sha256`. Fill those hashes into a **single
approved `generate` native request** but do **not** execute it
through the source-stdout CLI. Use it as the nested
`native_request` below.

The private escrow command's own strict JSON input schema is:

```json
{
  "schema": "jeeves.desktop.native-source-escrow-cli.v1",
  "action": "generate-save",
  "project_root": "/private/checked-project",
  "target": "/private/escrow/new-001.source.json",
  "native_request": {
    "schema": "jeeves.desktop.headless-native-source-work.v1",
    "action": "generate",
    "project_root": "/private/checked-project",
    "model_root": "/private/installed-approved-gguf",
    "state_dir": "/private/jeeves-sqlite",
    "tenant": "local",
    "subject": "operator",
    "goal": "Build one original helper and update an existing module",
    "format": "mixed-work",
    "maximum_attempts": 2,
    "source_paths": ["src/main.py"],
    "source_context_sha256": "<full original source-context SHA-256>",
    "job_sha256": "<full inspected job SHA-256>",
    "context_tokens": 4096,
    "max_output_tokens": 1024,
    "threads": 4,
    "gpu_layers": 0,
    "inference_ms": 90000,
    "capacity_budget_bytes": 8000000000
  },
  "expected_job_sha256": "<same inspected job SHA-256>",
  "expected_file_sha256": null,
  "expected_file_bytes": null,
  "recheck_original_source": false
}
```

Use actual full hashes, never angle-bracket placeholders, for
a real task. If no existing files are selected,
`source_paths: []` and
`source_context_sha256: null`.
The target must be a **new** filename ending in
`*.source.json`, underneath a pre-existing
owner-private `0700` directory **outside the original
project, installed model root and SQLite state root**.

The saved package includes private generated source, and
may include original source context from model edits.
Treat the storage root as confidential.

## Exact command

```bash
# Both grants are independently required for one new private source file.
# This ONE invocation starts one native generation and one private save.
python -m skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_native_proposal_cli \
  --approve-native-generation --approve-private-storage \
  < /private/task-with-escrow.json
```

Without **both** flags, the command fails before native
startup. The JSON cannot smuggle either grant as an extra
field. It rejects duplicate JSON keys, nonfinite values,
unsafe/relative paths, wrong project root, unrecognized
schema/authorities, a missing full inspected task SHA,
unknown or malformed nested native requests and a
destination which already exists.

Before constructing the GGUF, it checks the private
parent-directory inode, owner and permissions, plus
the destination's absence. No later race can overwrite
an existing file because publication uses
`O_CREAT|O_EXCL|O_NOFOLLOW` underneath the pinned
directory descriptor.

The already-installed offline model then undergoes
live source/rights, CPU/RAM/cgroup/disk preload
admission. The existing native bridge owns a single
principal-bound SQLite session and executes at most the
explicitly selected number of new SHA-committed
source-repair turns. The original project file
context is checked before and after each turn.

Once the native result is `review-required`, the
escrow layer **independently re-parses and rechecks**
the exact original generated source:
new paths must still be absent; old files must still
match independently computed original SHA; Python,
JSON and TOML must satisfy their no-execution syntax
gate; the Python cross-file import graph must not
contain an impossible relative import; the generated
plan's entire source-manifest and patch SHA must
exactly match the authoritative native/SQLite receipt.

The source package is then written exactly once
as a `0600` regular file under the existing
`0700` parent. The operation uses bounded writes,
`fsync`, inode/mode/link-count verification, a
complete byte readback and one last original-project
source check before returning a success receipt.

A saved private proposal contains:
- original task/job SHA and selected-source-context SHA;
- source-manifest and Git patch SHA for the **exact**
  reviewed generated source;
- original native model SHA, committed SQLite session
  and number of committed repair attempts;
- actual generated source JSON and its full SHA/byte size;
- offline static syntax status and Python dependency-graph SHA;
- explicit `original_checkout_modified=false`,
  `generated_code_executed=false`,
  `git_commands_executed=false` and
  `release_certified=false`.

**Only the owner-private file contains source text.**
The CLI's stdout receipt contains the model/session
and source digests, status and finite counts, not the
proposal, private project root or generated code.

If the model result is malformed/held, no file is
created. If the model successfully committed but
private publication fails, the CLI emits the original
native/SQLite identities and reports
`native-committed-private-publication-held`.
Do **not** run native inference again as a retry:
inspect the original SQLite session and failed
private location, then create a separately
reviewed task if needed. This avoids duplicating
potentially committed native work.

## Cold verification without another GGUF invocation

Later, another terminal process can verify the saved
file using only the original expected SHA and bytes
from its public save receipt:

```json
{
  "schema": "jeeves.desktop.native-source-escrow-cli.v1",
  "action": "verify",
  "project_root": "/private/checked-project",
  "target": "/private/escrow/new-001.source.json",
  "native_request": null,
  "expected_job_sha256": "<full inspected job SHA-256>",
  "expected_file_sha256": "<full private file SHA-256 from save receipt>",
  "expected_file_bytes": 6400,
  "recheck_original_source": true
}
```

Use `recheck_original_source: false` if the
original working tree is temporarily unavailable
and you only want to confirm the original owner-private
file's exact bytes, ownership, link count, mode and
canonical metadata. Use `true` to additionally
reread the current project source and confirm
that all original paths, file hashes, new-file absence,
supported language syntax and Python import graph
still match the saved proposal. A changed current
project must cause a **hold**, never a silent rebase
or automatic code edit.

Run without either execution approval:

```bash
python -m skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_native_proposal_cli \
  < /private/escrow/verify-request.json
```

This **never starts a GGUF or touches the SQLite
execution ledger**, reissues a model request, or
returns private source text in stdout.

## Operator-controlled source delivery after verification

A cold-verified saved source is not applied. Read the
private `proposal` string from the file **only inside
the trusted local environment** and pass it to the
independent `desktop_work_cli` in the appropriate
`mixed_work`, `new_files` or `existing_edits`
field. That CLI rereads actual project source, creates
an original operator-reviewable Git patch, verifies
syntax/graph and reports **new current exact source
and patch SHA-256 values**.

Only then may the operator separately approve
`--approve-private-stage` or
`--approve-private-patch`. These write a distinct
private overlay or inert Git patch, not the source
checkout. Applying changes to a Git branch, running
generated code, CI and release require still
separate controls.

## Trust and hardware limitations

All private proposal writers and cold readers use
POSIX/WSL2 descriptor-rooted file custody. Native
Windows reparse-point safety remains unqualified.
The maximum source proposal is 16 KiB and the whole
canonical private file is limited to 32 KiB. Output
names are tightly bounded. Existing files, hardlinks,
symlinks, shared folders, changed original sources,
modified source SHA, invalid supported syntax and
unverified original-session identities are denied.

The model cannot invoke storage, choose paths or
grant itself extra tools. Source strings are always
inert data. Permissions protect confidentiality
from other OS users but not from the same logged-in
user; this is not encryption.

The source-only regression suite uses an already
committed synthetic native receipt to exercise
the real project-source and private-file custody
without testing real GGUF weights. Its tests cannot
certify a physical Windows 11/WSL2 laptop, licensed
third-party model, actual GPU throughput, device
pressure or consumer release. All required exact-head
security and device acceptance remain held.

## Direct no-code-stdout delivery after saving

The new `desktop_native_source_delivery_cli` can cold-open
the saved proposal, recheck all current original source
files, reproduce exact Python graph/static source and
source-manifest/Patch SHA values, then—only after a
second separate full SHA and CLI approval—stage final
source files or export an inert Git patch directly.
There is no private code copied through stdout and
no new GGUF/SQLite inference. Complete flow:
`docs/ai/JEEVES_NATIVE_ESCROW_TO_STAGE.md`.
