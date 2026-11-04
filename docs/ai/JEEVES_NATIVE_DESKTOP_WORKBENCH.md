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
