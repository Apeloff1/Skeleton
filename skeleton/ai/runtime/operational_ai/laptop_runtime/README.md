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
