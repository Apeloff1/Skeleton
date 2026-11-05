# Jeeves local GGUF — bounded source-generation and structural self-repair

This is the operator-facing workflow for actual offline source authorship on
the already installed Jeeves GGUF model. It connects the real native
SQLite-committed conversational model to the reviewed Git patch, structural
source qualification, and conservative source-reconciliation subsystems.

A model alone cannot reliably build a correct source file in one turn.
A bounded repair loop lets it respond to meaningful, **sanitized actual
parser diagnostics** without granting filesystem, shell, Git, network,
hosted provider or write permissions.

## First use

1. Independently install an approved GGUF and open an existing model-bound
   SQLite chat session in the desktop. Native startup remains protected by
   the source-rights/manifest fence, the current RAM/cgroup capacity gate,
   and optional live pressure supervision.
2. Enter a concrete original coding task in the main prompt and choose
   **Generate source with bounded repair**. Select the trusted project
   directory yourself. A model cannot choose or reopen other directories.
3. Choose the actual source format: `new-files` uses
   `jeeves.workspace.new-files.v1`; `existing-edits` uses
   `jeeves.workspace.existing-file-edits.v1`. Existing-file edits require
   full, independently supplied original file SHA-256 values.
4. Select the maximum **one to three distinct native model turns**.
   Read the consent explaining that each attempt is a different committed
   model request on the *same* local GGUF/SQLite source. No attempt
   authorizes an automatically retried uncertain inference.
5. Choose **Generate with explicit finite repair**. The app takes the
   existing desktop bridge's exclusive one-worker lease for the entire
   approved task, then submits the original source instruction to the
   canonical `turn` IPC endpoint with a new visible `r_` request ID.
6. A successful native response must match the original SQLite session,
   exact installed model SHA, original request ID, output SHA-256,
   `authoritative_commit=true`, `replayed=false`, and
   explicit `device_qualified=false` and `release_certified=false`.
   An inconsistent receipt is a **terminal hold**, not another model call.
7. The exact returned JSON is parsed by the existing descriptor-rooted
   source reviewer. Original file bytes and SHA-256 are verified
   independently, all proposed new destinations must still be absent,
   and a complete portable Git patch is constructed only as inert data.
   Python/JSON/TOML replacement files receive non-executing structural
   qualification. Unsupported formats are clearly `unverified`.
8. If a supported parser rejects the proposal or the exact JSON schema
   does not match the selected format, the UI records the original
   committed request ID and a small, non-sensitive diagnostic code.
   While still within the **operator's original 1–3 turn budget**,
   a separate native turn asks the same GGUF to correct the entire
   strict JSON proposal, including its previous output as untrusted
   data. No failed turn ID is resubmitted. An oversized proposal
   stops the repair rather than increasing resource limits.
9. If a verified source proposal appears, the UI displays the original
   candidate and offers **Open COMPLETE operator patch review**.
   The new review window has **no manifest or patch digest approved**.
   You must independently read and confirm both SHA-256 values,
   revalidate source, and separately export a new no-clobber private
   Git patch before any manual application. The model cannot click
   this approval or create source files by itself.
10. Any terminal native error, model/source epoch mismatch, source
    collision, stale original hash, exhausted attempts or explicit
    **Stop AFTER current native turn** preserves the original visible
    run IDs and never creates a silent retry or Git operation.

## One worker, existing SQLite and no extra tools

This uses the canonical `DesktopBridge.request("turn")`, existing
`NativeJeevesChat`, single installed GGUF, native model/source fence,
and authoritative SQLite commit and replay verification. The source
repairer does not own an independent transcript, issue a fresh
session, import a second model, call hosted APIs or create a daemon.

The bridge's `exclusive_batch` lock spans the *entire* repair
sequence, preventing another chat or batch from interleaving with
a source task at a model-call boundary. A human can stop between
native turns; stopping an in-flight inference forcibly could leave
an uncertain SQLite effect, and this feature does not pretend to
safely cancel it.

The returned `jeeves.desktop.native-source-repair.v1` receipt
contains the original goal SHA-256, installed model identity,
source manifest/patch hashes if available, per-attempt original
SQLite request IDs, output hashes and finite diagnostic codes.
It deliberately does not include private absolute project paths,
original model-generated source text, prompts, signing keys,
session credentials or a claim of actual release.

## Explicit limits

- Original operator source goal ≤4,096 UTF-8 bytes.
- At most **3 distinct** canonical committed model requests, each
  under the real native input/output/context token and wall-time
  limits already enforced by the worker.
- Each committed source proposal ≤16,384 UTF-8 bytes; larger output
  is a terminal hold, not a signal to retry with expanded permissions.
- Diagnostic context ≤4,096 UTF-8 bytes and at most 10 controlled
  path/code/line diagnostic entries. No raw traceback or private
  exception text reaches a model or public receipt.
- Original project source review is still bounded to the desktop's
  existing file/byte/depth and no-symlink/credentials rules.
- No project writes, Git index writes, external shell, build scripts,
  compilation or arbitrary model tool calls. The operator remains
  responsible for every eventual source/patch application.

A parser-clean result is **not** an independently executable
product. It does not prove package imports, TypeScript/JS/Rust/C++
compilation, tests, dependencies, deployment, native GGUF device
performance or legal model rights. It must not be counted as a
release or Windows 11/WSL2 laptop certification.

The source-only regression suite covers a failed Python syntax
proposal repaired by a second unique SQLite turn, JSON schema
repair, exact receipt and answer SHA fencing, no-tool enforcement,
source file privacy, stale model/session epochs, operator stop,
bounded exhaustion and unreplayed uncertain result handling.
Physical device and real installed GGUF acceptance remain
separately required.

## Operator-selected exact original source for existing-file edits

The native source-repair window now supports **one to four** explicitly
selected existing project files before requesting a replacement.
**Review original SHA + full text** descriptor-reads the actual file
bytes and full original SHA-256, displaying the complete context
locally. The same GGUF receives those facts as untrusted reference
data, and revalidates original inode, byte hash, mode, ctime and
root on every turn. This removes the prior need to ask the GGUF
to invent original edit SHA-256 values. The source manifest is
included in the final human-only receipt; no model filesystem
permission, direct file overwrite or Git commit is granted. See
`docs/ai/JEEVES_OPERATOR_PROJECT_SOURCE_CONTEXT.md`.

## Mixed new+existing project work in one real local GGUF response

Choose **`mixed-work`** to propose new source files AND edits
to existing project files in one SQLite-committed native response.
This combines the original strict new-file and old-file hash
reviewers without extending model permissions. It works with
the operator-selected exact original source context and
bounded self-repair turns. After verification, the mixed
response opens a fresh human-only Git patch review, not an
automatic application or branch push. Full schema and
operator flow: `docs/ai/JEEVES_NATIVE_MIXED_PROJECT_WORK.md`.

## Terminal-first native coding without the desktop GUI

`python -m skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_native_code_cli`
runs the *same* source-repair loop on the *same* installed GGUF
and SQLite child without Tk. A read-only `inspect` hashes
the operator's task, source selection and resource budgets.
A second `generate` call must reproduce those exact hashes
and carry `--approve-native-generation` before a single
new native/SQLite session can start. The CLI never runs Git,
writes original sources or prints raw source code unless an
additional `--emit-private-proposal` flag is supplied.
`docs/ai/JEEVES_HEADLESS_NATIVE_CODE_GENERATION.md`.
