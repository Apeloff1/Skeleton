# First usable offline AI laptop runtime (real GGUF, not game features)

This interface uses the existing canonical `ExecutionSpine` plus
`SupervisedAI`, verified local llama.cpp GGUF backend, isolated native worker,
private principal-bound SQLite state, and the existing hardened bearer HTTP
server. It does **not** create an alternative text-generation engine.

## First-use graphical workbench

Jeeves now has a local desktop UI backed by the same installed GGUF native
child and authoritative SQLite session owner. Launch from a trusted checkout
with Python/Tk and the independently installed model:

```bash
python scripts/launch_jeeves_desktop.py
# or ./jeeves-desktop.sh on Linux/WSL2
```

The workbench offers approved bundle installation, read-only model inspection,
one private state-root preparation, explicit source/capacity activation,
multiline source-bound chat, durable new/resume/close/history, finite
principal-bound SQLite conversational context and deliberately selected
read-only text/code attachments. No second model, extra memory store, hosted
fallback, web listener, automatic native retries or auto-applied code edits
are created. Native source loss is terminal and unqualified physical devices
remain held. Full operator guide:
`docs/ai/JEEVES_NATIVE_DESKTOP_WORKBENCH.md`.

## Source-bound first-install flow

1. Install an operator-approved, digest-pinned GGUF package using the existing
   ordered ecosystem installer; ensure that the model receipt binds actual bytes,
   archive digest, source SHA and independently approved rights. The installer
   does not ship any synthetic model files or claim licensing review itself.
2. Provision the private local state directory and required principal binding.
   On Linux, use the existing 0700/0600 descriptor-anchored model and state
   custody; Windows/WSL2 still requires target-device qualification.
3. Invoke the new operator CLI with `--mode once --prompt-stdin`, or start
   `--mode serve` with a high-entropy `SKELETON_LOCAL_AI_BEARER` environment
   value. Prompt text enters via stdin, not process command arguments.
4. A source-bound receipt is checked before the real native engine activates;
   the actual active model hash is then matched against installed bytes.
5. A committed turn comes from the existing supervisor/SQLite execution spine;
   replay reads its durable receipt without a second inference.

## Operator examples

```bash
python -m skeleton.ai.runtime.operational_ai.laptop_runtime.cli \
  --mode once --model-root /private/installed-gguf \
  --state-dir /private/state --tenant local --subject operator \
  --prompt-stdin < /private/prompt.txt

python -m skeleton.ai.runtime.operational_ai.laptop_runtime.cli \
  --mode serve --model-root /private/installed-gguf \
  --state-dir /private/state --tenant local --subject operator \
  --port 8765

python -m skeleton.ai.runtime.operational_ai.laptop_runtime.qualification.cli
```

Never put private tokens or private prompts into repository files or shell
command arguments. The browser HTTP surface is intentionally disabled by Host,
Origin and bearer gates; tools, network actions, implicit memory and model
upgrades cannot be authorized by generated text. Current native streaming is
**post-commit output chunking only**, not live token delivery.

## Qualification is not a local code metric

Source-controlled 26-boundary casebooks execute 364 policy/typed-input
examples. They do not load a real model, install Windows, verify third-party
model rights or prove device throughput. Additional real GGUF-first-turn,
durable restart/replay, cancellation, clean install, exact-head CI/security
and independent review remain mandatory. No missing/skipped/pending/failing
workflow is a pass.

## Human-approved new-source delivery

The desktop's separate source-review window can publish one operator-reviewed
new file at a time with a no-clobber SHA-256 manifest. It never lets model
output overwrite existing files, execute code, create workflow authority or
acquire a filesystem tool. Use the complete guide at
`docs/ai/JEEVES_WORKSPACE_NEW_FILE_DELIVERY.md`.

## Hardware-aware advisory startup

The desktop may inspect the installed model, host memory and effective
cgroup v1/v2 CPU/RAM limits **before** real startup, then propose CPU-only
resource bounds. This is read-only advisory sizing, not GPU/VRAM detection
or certification. A connected operator can inspect actual supervisor
capacity/circuit statistics without invoking generation.

## Strict native Jeeves agent action

Alongside SQLite chat, the UI can execute bounded multi-step reasoning through
the existing `NativeJeevesRuntime` and `StrictJeevesAgentRuntime`. It
reuses the live installed GGUF and source guard, with an empty tool registry,
zero grants and a finite request/run budget. The UI never treats model output
as permission to modify the host. The separate durable agent CLI remains the
explicit restart-safe lane; desktop reasoning does not silently resume work.

## Durable work in the same SQLite owner

Explicit start/inspect/resume/replay actions are available through the
desktop's native work-order controls. They delegate to the existing
`NativeDurableJeevesAgent` under one source-fenced GGUF worker and original
run/task/budget/tenant/model journal identity. No automatic resume or new
memory database is created; uncertain pending native effects fail closed.

## Operator-only project source discovery

Search a bounded local code tree with **Search project sources** and manually
attach an exact UTF-8 excerpt to a later native prompt. Source indexing has
no model tool authority, follows no symlinks, excludes protected control and
credential paths, and labels incomplete budget-limited searches. Full
boundaries: `docs/ai/JEEVES_LOCAL_SOURCE_DISCOVERY.md`.

## Existing-file edit candidates

The desktop reviews model-proposed changes to existing source, verifies
original content hashes, shows full unified diffs, and permits an operator
to stage a single inert no-clobber sibling candidate per full SHA approval.
It NEVER overwrites the original; explicit editor/Git application is
separate. `docs/ai/JEEVES_EXISTING_SOURCE_EDIT_REVIEW.md`.

## Optional read-only signed source agent

The desktop agent can explicitly opt into the existing
`jeeves_signed_source_lookup` via a host-verified signed source manifest,
independent operator HMAC key, installed model/tokenizer identity and finite
source/call grants. Off by default. Original source bytes are verified
before native startup and before/after each strict agent run; no tool
authorizes writes. `docs/ai/JEEVES_DESKTOP_SIGNED_NATIVE_SOURCE_AGENT.md`.

## Adaptive host pressure protection

The GUI may supervise the live GGUF child with measured host RAM,
effective cgroup memory, local state disk and process RSS. Sustained
pressure or unknown kernel telemetry revokes that same native child
without automatic inference retry. This is a conservative pressure
guard, not GPU memory offload. Detailed thresholds and holds:
`docs/ai/JEEVES_NATIVE_PRESSURE_SUPERVISOR.md`.

## Advanced native reasoning profile

The desktop's explicit `advanced` profile configures bounded planning,
replanning and model verification using the existing
`StrictJeevesAgentRuntime` against the same one installed GGUF and SQLite
owner. It cannot raise tool permissions, start other providers or stage
persistent memory. `docs/ai/JEEVES_ADVANCED_NATIVE_REASONING.md`.

## Serial durable native work

Operator-approved `jeeves.desktop.durable-work-batch.v1` tasks run
sequentially through one connected GGUF and the original sealed SQLite
work journal. Each run ID is minted and approved before inference.
No automatic retry/resume or source write is granted.
`docs/ai/JEEVES_SERIAL_DURABLE_WORK_BATCHES.md`.


A serial work batch now holds an **exclusive native bridge lease for its
entire source-approved manifest**. Other desktop request threads are refused
before IPC, including other batches; the pressure watchdog retains terminal
revocation authority. No automatic native retries or source/tool escalation.

## Cold-restart batch recovery

The serial work-batch GUI can explicitly export the **complete original**
task budget/ID manifest to a *new* descriptor-anchored owner-private `0600`
file under a pre-existing private `0700` POSIX/WSL2 directory. Imported
recovery batches cannot be started or resumed; only a selected original
work order's sealed SQLite checkpoint may be inspected or replayed after
the operator supplies the exact original manifest digest. Nothing is
silently reissued. Sensitive task text is present in the private export;
never put it into Git. See
`docs/ai/JEEVES_PRIVATE_BATCH_COLD_RECOVERY.md`.

## Fresh pre-load host/CPU/cgroup admission

With protected desktop startup enabled, `desktop_preload_admission.py`
rereads installed GGUF rights/source and measures current RAM, effective
cgroup limit/CPU quota, SQLite free disk and conservative context/scratch
working memory before the native loader. A stale advisory profile cannot
authorize an oversized model. The original resource request stays unchanged,
and a typed source-bound ready receipt is verified by the UI parent.
`docs/ai/JEEVES_FRESH_PRELOAD_HARDWARE_ADMISSION.md`.

## Portable reviewed Git patch export

Use **Build reviewed Git patch** to combine exact new-file proposals
and checked original-file edits into one Git-compatible source artifact.
An operator reviews the entire unified diff, confirms full source
and patch SHA-256, then exports a NEW private `0600` patch outside
the original workspace. The model gains no shell, Git index, or file
write grant. The exported bytes may be manually checked with
`git apply --check` before any separate operator-authorized
application. `docs/ai/JEEVES_PORTABLE_GIT_PATCH_DELIVERY.md`.

## Offline parser qualification for generated source

Before an operator-approved private Git patch export, Jeeves checks
generated Python (AST), JSON (strict duplicate/NaN rejection), and
TOML (stdlib parser) without executing source. Invalid supported
syntax holds the export. TS/JS, YAML, SQL and other unsupported formats
remain marked `unverified`; parser success is never called a build,
runtime test or release qualification. See
`docs/ai/JEEVES_STATIC_SOURCE_QUALIFICATION.md`.

## Conservative source-drift reconciliation

The reviewed Git patch window can now reconcile original source changes
made by another editor, preserving independent line hunks and holding
overlap/conflicts. It creates only a NEW unapproved JSON proposal,
never a project write or Git apply. The prior SHA authorization is
invalidated, with complete fresh review required before export.
`docs/ai/JEEVES_CONSERVATIVE_SOURCE_REBASE.md`.

## Bounded native model self-repair for source proposals

The local installed GGUF can now generate strict source JSON,
review actual original project bytes, run a static syntax check,
and take at most three distinct SQLite-committed model turns to
repair source errors. Operator consent is required before the loop;
each request has a new visible original ID. Only an unapproved
inert proposal is produced; no Git, shell or project write tool
is granted. Full human approval and private no-clobber patch export
are separate. See `docs/ai/JEEVES_NATIVE_SOURCE_SELF_REPAIR.md`.

## Operator-reviewed original project source context

The native source-generation/repair window now lets the operator select
up to four exact trusted original files (8 KiB total), inspect their
complete contents and SHA-256, and provide that snapshot as
JSON-escaped reference DATA to the same installed GGUF. Every native
turn rechecks the original bytes, inode, ctime and ownership before
accepting source work; stale or untrusted source holds instead of
being retried. Existing-file edits can now use independently verified
original SHA-256 values without a manual hash-entry prerequisite.
`docs/ai/JEEVES_OPERATOR_PROJECT_SOURCE_CONTEXT.md`.

## Mixed new/existing source generation

The native source-repair GUI includes **mixed-work**, allowing
one local GGUF SQLite turn to propose new source files plus
independently SHA-verified changes to existing files. The
decoder rejects unexpected authority, duplicate paths and
mismatched original hashes; the exact result passes through
existing new-file/edit reviewers, the static parser and a
fresh operator-approved Git patch export. No direct source
writes, Git tool grants or automatic publication are added.
`docs/ai/JEEVES_NATIVE_MIXED_PROJECT_WORK.md`.

## Sealed private source-overlay stage

The Git patch review window now offers an explicit standalone
**Stage reviewed SOURCE files privately** action. It renders
the exact final new/edited source into a brand-new owner-private
`0700` folder with `0600` files and hash manifest, writing
the complete seal **last**. The original project is revalidated
before staging and never modified; the product never executes
model-generated source, runs Git, or grants the model arbitrary
writes. Incomplete/tampered stages fail verification. The strict
mixed-work parser now enforces the native 16 KiB reply ceiling.
`docs/ai/JEEVES_PRIVATE_SOURCE_OVERLAY_STAGING.md`.

## Strict headless local source-work command

Run `python -m skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_work_cli`
with a bounded strict JSON source-work request on stdin. It can
review mixed new/edit proposals, report syntax status, inspect
conservative source conflicts, cold-verify private patch/stage
artifacts, or—only with **both exact full SHA-256 values plus
an explicit separate CLI flag**—create a new sealed private
source overlay or inert Git patch. The model, source checkout
and Git remain inactive. Documentation:
`docs/ai/JEEVES_HEADLESS_LOCAL_SOURCE_WORK_CLI.md`.

## Source-bound Python dependency graph

The native coding workbench now analyzes imports across the
exact reviewed Python changes. Known edges to other reviewed
files, unknown original/external packages, invalid relative
levels and observed cycles are separately reported under
one graph SHA-256. Impossible relative imports block the
private stage/export, while external imports remain
unverified rather than falsely passed. All analysis is
AST-only and non-executing:
`docs/ai/JEEVES_OFFLINE_PYTHON_SOURCE_GRAPH.md`.

## Real native local GGUF source generation from a headless terminal

`python -m skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_native_code_cli`
now closes the Tk-only gap: explicit `inspect` proves the
original task, resources and selected existing-file SHA-256;
a separately approved `generate` launches the existing
real local GGUF/SQLite worker, enforces preload hardware
admission, executes finite distinct source-repair turns
and reports SHA-bound review evidence. A second explicit
flag permits optional private model source output, but
no generated code is automatically applied, executed or
committed. Full instructions:
`docs/ai/JEEVES_HEADLESS_NATIVE_CODE_GENERATION.md`.

## Private GGUF source proposal handoff (without stdout disclosure)

The separately approved
`desktop_native_proposal_cli` combines one
exact-inspected local GGUF/SQLite source work request
with a new no-clobber owner-private `0600`
`*.source.json` file under an existing `0700`
directory. Model code never appears in stdout,
and the saved source is cold-verifiable by full
SHA-256, original model/session, exact source
manifest/patch and current source checks without
retrying inference. Application to Git/project
remains separately reviewed and authorized.
`docs/ai/JEEVES_NATIVE_PRIVATE_SOURCE_ESCROW.md`.

## Cold native escrow to explicit private source/patch delivery

`desktop_native_source_delivery_cli` now connects the
headless GGUF-to-private-proposal custody directly with
the same guarded new/edit source staging and Git patch
export used by the Tk workbench. A cold read rechecks
the entire private file and current real workspace,
including full source/patch/graph SHA. A second CLI
action needs both full operator-approved hashes plus
`--approve-private-stage` or `--approve-private-patch`.
Neither operation starts a model, executes source, changes
the original project or invokes Git.
`docs/ai/JEEVES_NATIVE_ESCROW_TO_STAGE.md`.

## Native source-campaign review and goal composition

The advanced local-only Jeeves coding campaign uses a single operator-visible
workbench. It runs only through the existing GGUF/SQLite ownership and
separately verified source-custody authorities. A read-only task composer can
prepare SHA-bound original-source jobs; independent explicit approvals are
required before inference or patch publication. Never treat source drafts
or model text as executable code. The original project remains unchanged.

- `docs/ai/JEEVES_NATIVE_CAMPAIGN_SOURCE_ASSEMBLY.md`
- `docs/ai/JEEVES_NATIVE_CAMPAIGN_DESKTOP.md`
- `docs/ai/JEEVES_NATIVE_CAMPAIGN_GOAL_COMPOSER.md`
