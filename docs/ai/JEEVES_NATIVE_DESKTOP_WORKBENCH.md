# Jeeves — offline native desktop workbench

The first-laptop workbench is an interactive **local model application**, not
a synthetic AI demo. It uses the existing approved GGUF installer, native
`IsolatedGGUFBackend`, capacity lease, `SupervisedAI`, canonical
`ExecutionSpine`, private principal-bound SQLite and
`NativeJeevesChat`. Tkinter is only the window. There is **one installed
model, one SQLite authority and no remote inference fallback**.

## Launch

From a trusted checkout with Python 3.11+, Tk/Tcl installed, and an
operating-system-supported environment for the existing descriptor-anchored
installer (Linux or WSL2 with a GUI such as WSLg):

```bash
python -m skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_app
# or
python scripts/launch_jeeves_desktop.py
```

On Ubuntu/WSL2, Tkinter may need an explicit `python3-tk` installation from
your trusted system package source. The workbench does not install packages
itself. **Native Windows 11 is not qualified by source-only code.** The
installer and model state guards require POSIX descriptor semantics; use WSL2
only after independently validating the target device, including GUI, private
mounts, model runtime and memory pressure.

## First run: real offline model, not generated weights

1. Obtain an authorized ordered `skeleton-ai-ecosystem` model package from a
   source you have independently reviewed. The app never downloads weights,
   licenses an external model or infers permissions from the model output.
2. In **Prepare / install approved local model**, select an existing trusted
   private installation parent, the archive, manifest model ID and a new
   installation ID. **Install approved bundle** invokes the existing
   descriptor-anchored `install_approved_model` with exact archive hashes,
   manifest inventories, typed GGUF shards and atomic no-clobber publication.
3. **Inspect model** re-hashes installed source bytes without native inference.
   This checks content, not independent ownership of third-party rights.
4. **Prepare private state** creates one 0700 directory under a trusted
   existing parent. It does not overwrite or adopt an old database or create a
   mismatched principal binding; canonical startup owns the exact
   tenant/subject/model/tokenizer state binding.
5. Enter installed model root, private state directory, tenant, subject,
   context, CPU/GPU and capacity limits. Click **Connect native**.
6. The private child must independently validate source, rights, live
   isolated GGUF, resource capacity and SQLite before publishing the
   `native-gguf-ready` frame. If any gate fails, there is **no fallback**.
7. Type a prompt (multiline Unicode/code supported) and choose **Send
   locally**. The app generates a unique request ID and sends the prompt
   through a binary pipe, not a process command-line argument or HTTP route.
   The authoritative SQLite replay must confirm the native model receipt
   before any answer is displayed.

The model and tokenizer hashes are checked at every operation by the existing
native source guard. Source revocation, changed owner, lease loss, malformed
response, partial output, crash or uncertain native effect terminate the
child and **never automatically retry the request**.

## Conversations and context

**New session** creates a new private SQLite session under the same GGUF
worker. **Resume** authenticates an existing session ID against the same
principal/model SQLite authority. **SQLite history** reads the source of
truth; the window does not maintain another transcript database.
**Close session** closes one canonical session. **Disconnect** shuts down
the worker but preserves any unclosed committed conversation for later resume.

The optional **Use recent committed SQLite turns as bounded context**
checkbox defaults to enabled. The host constructs a deterministic source
envelope from at most twelve recent owner-scoped user/assistant records and
limits historical content to 12 KiB before calling `NativeJeevesChat.turn`.
It never edits an old receipt, silently truncates the *current* user prompt,
uses generated text as tool authorization or accesses another session.
Older context messages are removed whole when over budget. The canonical
prompt+request-ID is still committed and replay-verified in the same SQLite.
History display unwraps its original-user text with an exact SHA-256 check.

## Local selected source attachments

**Attach text/code file** snapshots up to four explicitly selected regular
text/code files, 16 KiB each, 24 KiB aggregate before prompt overhead.
The file is opened read-only with final-component no-follow; its byte
identity, source inode and size are checked before/after reading. Only exact
UTF-8 data is accepted, with a SHA-256 shown to the operator. The selected
content is included as **reference data in the local native prompt**, never
an automatically executable tool, network upload, file modification or
extra memory authority. The file snapshot is held only in window memory and
cleared after a confirmed committed native response.

## Private IPC and resource limits

The child speaks a deterministic 4-byte length-prefixed UTF-8 JSON framing
protocol through an unshared stdin/stdout pipe:

- Incoming frames no larger than 64 KiB; prompts no larger than 32 KiB.
- Outgoing frames no larger than 256 KiB; whole-session publication budget
  16 MiB; 1,024 explicit commands per native process by default.
- JSON duplicate keys, ambiguous fields, malformed UTF-8, non-finite numbers,
  extra commands, wrong source/tenant or incomplete writes terminate safely.
- One UI-managed request is in flight at a time. The child remains
  source-bound and each chat turn uses the authoritative native SQLite
  replay and native session critical section.
- The startup process is killed after a bounded configured timeout.
  A failed/uncertain native request is never transparently reissued.

No websocket, external HTTP listener, provider API token, implicit file
execution, invented device-rights evidence or hidden persistent chat store
is created by the desktop workbench.

## Qualification and remaining physical work

This code provides a concrete desktop runtime, not consumer release approval.
A successful source-only test or mocked dialogue is not an actual GGUF call.
The target laptop still needs an independently licensed installed model,
full live first turn, cold process/SQLite replay, WSL2/Windows installer
verification, native cancellation, CPU/GPU/memory/disk pressure qualification,
and required exact-head security/release gates. Do not infer 100% readiness
from file counts or CI alone.

A user-supplied source file may contain prompt-injection instructions; its
text remains **untrusted reference data** and cannot gain host tool
permissions. The app currently has no automatic source-editing or patch
application feature.

## Explicit local new-file builder

The desktop also supports a real, narrowly scoped source-delivery step.
Click **Insert source proposal format** to ask the existing GGUF for strict
JSON, then **Review Jeeves file proposal** to inspect the model's untrusted
answer. Choose the local workspace, inspect each SHA-256 and unified diff,
and individually confirm the full digest before publishing that **one NEW
file**. Existing paths are never overwritten. The publisher performs
descriptor-anchored, symlink-safe, no-clobber, fsynced writes; it neither
executes the proposed source nor grants autonomous tools.

Detailed source contract, usage and limitation notes:
`docs/ai/JEEVES_WORKSPACE_NEW_FILE_DELIVERY.md`.

Source-only qualification of this file writer cannot establish model
correctness or consumer-device readiness.

## Effective CPU/RAM admission and live capacity

Before connecting, click **Suggest measured CPU/RAM profile**. This
read-only operator action verifies the installed GGUF source and rights
receipt, observes actual available host RAM, free state storage and the
effective process cgroup v1/v2 memory/CPU limits, and selects conservative
CPU-only native settings. It reserves room for operating-system RAM, model
weight bytes, a bounded KV-cache estimate and native scratch memory.
Unknown or conflicting metrics and insufficient available resources are
refused rather than represented as successful model admission. These figures
are estimates, not proven allocator footprints, and never substitute for the
native capacity broker or isolated GGUF activation.

The **Live capacity** button, available only while the native child is
connected, asks the same source-checked supervisor for its actual capacity,
model circuit and service metrics. It never performs inference or modifies a
running model. GPU layers remain zero by default because this source-only
planner has no verified VRAM/backend capability reading. Device-pressure,
swap, native cancellation and real Windows/WSL2 readiness still require
physical qualification.

## Bounded native request watchdog and cross-session custody

Each source-bound native response is matched against the exact issued
operation. A committed turn must retain its original SQLite session, request
ID, model hash and authoritative receipt; the UTF-8 answer SHA-256 is checked
before the window displays the text. A reply from an old worker cannot be
displayed after disconnect/reconnect. The private GUI and model are separate
processes, with no automatic replay of uncertain effects.

Each explicit turn has a watchdog capped at 660 seconds and normally
scheduled for native inference deadline plus 45 seconds of IPC/teardown
allowance. Read-only/control operations have a 30-second timeout. A timed-out
child is terminally revoked: the UI retains the original request ID for
manual committed-state reconciliation and does **not** regenerate a task
automatically. A source-revocation or partial response cannot be promoted
into a successful desktop turn.

## Strict Jeeves native agent mode

The desktop has two distinct actions against the **same** already admitted
isolated GGUF and source/SQLite authority:

- **Send local chat** appends one committed, principal-bound SQLite turn and
  can include explicitly enabled bounded historical conversation context.
- **Run native Jeeves agent** invokes the existing `NativeJeevesRuntime`
  with `StrictJeevesAgentRuntime`, bounded planning and verification,
  and an empty host tool registry. No network, shell, filesystem write,
  memory-promotion or hosted inference grant is created.

Agent defaults are 8 steps, 8 native model calls and 180 seconds; the operator
may reduce or increase them within 64 steps, 64 model calls and 600 seconds.
The desktop records a unique visible run ID and preserves it on timeout or
failure; all native effects remain subject to the original SQLite model
commit/replay and single-worker source contract. The host refuses to disclose
a successful agent reply if the strict runtime reports failure, resource
overrun, a tool effect, principal drift or source revocation.

The native client checks the agent's original run ID, source/model hash,
UTF-8 answer digest and strict zero-tool result before displaying output.
The operator may separately feed the returned text to the new-file review
window, but doing so never confers file-write permission. The GUI agent lane
is **in-process reasoning only**, not a claim of restart-safe durable agent
checkpoints; the existing separately guarded durable operator CLI remains
available for explicit cold recovery.

## Cold-restart-safe durable Jeeves work

The desktop **Durable work orders** controls delegate to the original
`NativeDurableJeevesAgent` and its one authoritative SQLite journal. These
are not auto-run jobs, a background task scheduler or a separate database.

Choose **New durable work** while a source-checked native worker is connected.
The UI allocates and displays a fresh immutable `wrun_...` ID. The worker
binds that ID to the **exact original task, maximum steps, maximum model
calls, wall-time budget, tenant, subject, model and tokenizer** before any
native work. Keep the run ID, task and budget values yourself. A later
connection may use **Inspect**, **Resume explicitly**, or **Replay terminal**
with precisely those original details:

- **Inspect:** read-only authoritative checkpoint state. Never regenerates
  or interprets a missing model outcome as success.
- **Resume explicitly:** only at the operator's instruction. The existing
  `NativeDurableJeevesAgent` checks the sealed chain, rejects pending
  generation uncertainty, unsafe tool steps, changed owner/source/input,
  terminal checkpoints and conflicting attempts.
- **Replay terminal:** reads a previously committed sealed SQLite result
  without creating a new model effect. A failed terminal run is a hold,
  not a false completed result.

No implicit tool grants, file edits, internet calls, memory promotion or
automatic native retries are created by the desktop. A failed or timed-out
run can be inspected explicitly after a new independently admitted worker
activation. The desktop does not automatically restart it.

The private binary bridge checks `run_id`, action, source/model digest,
verified terminal success, zero tool calls, release hold, exact answer
SHA-256 and the distinction between **native generation** and **read-only
inspection/replay** before displaying a result.

**Important:** The model must actually be approved and installed locally.
The source-level interface cannot certify physical CPU/GPU performance,
Windows 11/WSL2 installation, legal rights, native cancellation, or release.

## Search existing project source without model tools

Choose **Search project sources** to open the finite read-only project index.
It scans explicit operator-selected regular code/text files using pinned
local directory/file descriptors and finite depth, bytes, count and time
bounds. Search may match source text or the relative filename. The UI
presents exact hashed UTF-8 excerpts with line ranges, then requires a
separate **Attach selected exact snippet** action before a subsequent chat,
agent or durable-work prompt can use that text as untrusted reference data.
No search results are silently uploaded, memorized, executed or written back.
See `docs/ai/JEEVES_LOCAL_SOURCE_DISCOVERY.md`.

## Reviewed proposals for existing files

The desktop can now request full-replacement edits for existing source files
using the **Insert existing-edit format** prompt helper, then review the
committed model answer in **Review existing-file edits**. The proposal must
carry each original file's full SHA-256. The UI shows exact original-versus-
replacement diffs and requires a separate full digest confirmation for every
candidate. Its publication uses no-clobber, descriptor-anchored creation of
a *new* inert sibling; the existing file is not overwritten by Jeeves.
The operator must apply reviewed candidates in their own editor/Git workflow.
See `docs/ai/JEEVES_EXISTING_SOURCE_EDIT_REVIEW.md`.

## Advanced operator-signed source lookup

The strict native agent now optionally supports a **single read-only
operator-signed source tool**, disabled by default. The desktop verifies
HMAC, original bytes, tenant/model/tokenizer and expiry before loading
GGUF, then verifies the same identity at native binding and each run. No
unsigned source fallback or general file tool is permitted. See
`docs/ai/JEEVES_DESKTOP_SIGNED_NATIVE_SOURCE_AGENT.md`.

## Live native RAM/cgroup/disk pressure guard

The desktop can arm an operator-configured parent-side resource monitor
after an independently accepted local GGUF ready frame. It observes
actual Linux host RAM, cgroup limits, SQLite storage free bytes and
the native child's process-RSS identity. Persistent low headroom,
source-process replacement or unavailable telemetry revoke the isolated
worker without repeating uncertain native work. **Host pressure status**
displays only the latest bounded measurements. GPU/VRAM and native
cancellation qualification remain open. See
`docs/ai/JEEVES_NATIVE_PRESSURE_SUPERVISOR.md`.

## Advanced bounded native planning

The **Reasoning profile** control now selects either conservative guarded
reasoning or an explicit advanced profile. Advanced mode uses the existing
strict Jeeves runtime, up to 32 plan steps, finite replans, grounded
verification and deterministic model sampling, all subject to original
model-call/time/step and source permissions. Unsupported or under-budgeted
advanced requests are held, not silently downgraded. Profile receipts
state verification **requested**, never invent its successful execution.
See `docs/ai/JEEVES_ADVANCED_NATIVE_REASONING.md`.

## Sequential durable work batches

The desktop can accept an operator-reviewed, exact-SHA-256 manifest of
up to 32 sequential native tasks and run each **once** under a separate
visible canonical SQLite `wrun_...` work order. All tasks share one
source-fenced installed GGUF child; no parallel inference, hidden tool,
background task scheduler, second database or automatic replay is used.
A failed/uncertain task stops the entire sequence and preserves the
original run ID. See `docs/ai/JEEVES_SERIAL_DURABLE_WORK_BATCHES.md`.

## Measured preloader resource admission

When protected native startup is enabled, the child verifies real installed
model source and rights, current host/cgroup RAM, effective CPU quota and
SQLite free disk **before loading GGUF**. It checks a conservative
model/context/threads scratch estimate against both measured memory and the
original operator capacity budget, refuses unsafe shapes, and supplies
an exact typed receipt bound by the parent to the actual activated model.
It never silently changes threads/context or guesses GPU VRAM. See
`docs/ai/JEEVES_FRESH_PRELOAD_HARDWARE_ADMISSION.md`.

## Complete Git-native reviewable source changes

The desktop now combines new-file and existing-file Jeeves proposals
into one SHA-256-bound Git patch, with strict original-source rechecks
before exporting a brand-new owner-private `0600` source artifact
outside the project. The operator explicitly approves both original
manifest and final patch digests. Neither Jeeves nor the export
runs Git or overwrites live project source. Detailed operator workflow:
`docs/ai/JEEVES_PORTABLE_GIT_PATCH_DELIVERY.md`.
