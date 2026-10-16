# First install: AI chat and Dragon web capture

For the integrated studio workflow, see
[crawler, builder and training operations](STUDIO_CRAWLER_BUILDER_TRAINING.md).

The full application uses the existing frontend, backend, canonical AI engine
and Mongo services. This guide covers installation, optional local weights,
durable chat and bounded web capture. It does not certify production deployment,
every-console compatibility, studio mastery or automatic improvement in quality.

## Start the application

From the repository root, with Python and Docker Compose installed and the
Docker daemon running:

```bash
python scripts/install_app.py --production --start
python -m skeleton app doctor --live --json
```

The installer prepares Python dependencies and the private `.env`, generates
stable credentials and starts the existing Compose services. A later setup run
preserves valid credentials. Keep `.env` private. The installer does not install
Docker or grant operating-system privileges.

The default minimal startup creates required authentication/storage indexes and
defers bulk sample-library generation, automatic training and unrelated downloads.
The existing `DB_NAME` selects the backend Mongo database. Curiosity state uses
the existing backend data volume at `/app/data/curiosity`; the read-only container
root is not a writable state location.

Open `http://localhost:3000/setup` with the default ports. The setup page remains
readable before login and when the API is unavailable. It observes capabilities
separately and provides commands to copy into the host terminal. Create an
account through the existing login screen. A healthy application can have an
unconfigured AI model; the page reports that condition explicitly.

Public registration creates a viewer account. To operate captures and other
editor/admin features on a new installation, explicitly configure the owner
through the existing bootstrap before starting or recreating the backend:

```bash
python -m skeleton app setup --admin-email owner@example.com \
  --admin-password-file /absolute/private/owner-password.txt
python -m skeleton app up --production --no-build
```

The UTF-8 password file must be private (Unix mode `0600`), contain at least
16 characters and at most 72 UTF-8 bytes, and must not be a symlink. The password
is read from the file and never passed as a command-line argument or printed.
Keep the file and generated `.env` private. Sign in with this explicitly
configured account to manage roles through the existing administrator authority.
There is no shared default administrator password or automatic first-user
elevation.

The first-install continuation has been exercised with fresh Mongo, engine,
production backend and Nginx containers, including actual local-model inference,
account restart recovery and crawler controls. Desktop and mobile browser
operation used the final production web export. Exact results and qualifications
are in [the implementation report](../plan/JEEVES_FIRST_INSTALL_2026-10-15.md).

Use `python -m skeleton app status --live` to check the current service topology
and `python -m skeleton app logs` for service logs. The optional Chroma profile
is not required for bounded lexical retrieval from captured sources.

## Activate the reproducible local CPU model

The optional acquisition recipe uses Qwen3-0.6B-Q8_0, an Apache-2.0 model, and
llama.cpp b11429, an MIT runtime. Both artifacts have fixed URLs, exact byte
counts and SHA256 values in `scripts/provision_local_ai.py`. The runtime recipe
targets Linux x86_64 with glibc, including the canonical engine container. This
small model provides a usable integration path; useful complex planning still
depends on model capability and measured results.

Explicitly download and prepare approximately 657 MB of artifacts:

```bash
python scripts/provision_local_ai.py --target linux-x86_64-glibc --download --context-size 12288 --output ./data/local-ai
```

Alternatively, reuse the exact pinned files already acquired by the operator:

```bash
python scripts/provision_local_ai.py --target linux-x86_64-glibc --output ./data/local-ai \
  --model /absolute/path/Qwen3-0.6B-Q8_0.gguf \
  --runtime-archive /absolute/path/llama-b11429-bin-ubuntu-x64.tar.gz
```

Preparation verifies every artifact, materializes bounded regular runtime files,
preserves the runtime license and records all resulting file digests. It creates
a portable relative-path deployment through the canonical model loader. It does
not invoke a model, change `.env`, start a service or claim quality certification.
At least two GiB free disk space is required. The destination must be new, an
operator-owned safe empty directory, or a complete matching installation that
can be verified. Setup creates the default empty directory before Compose binds
it, so Docker does not create it under a different owner. Provisioning claims an
empty destination exclusively before writing. Incomplete destinations are never
treated as ready; after correcting a failure, choose a new directory. Existing
files are not overwritten.

Set the following values in private `.env` for the read-only Compose model mount:

```dotenv
AI_PROVIDER=local
AI_LOCAL_MODEL_PATH=
AI_LOCAL_DEPLOYMENT_PATH=/app/local-ai/deployment.json
SKELETON_LOCAL_MODEL_DIR=./data/local-ai
```

Leave external secondary provider and verification model settings empty in local
mode. Then recreate the engine through the existing app command:

```bash
python -m skeleton app up --production --no-build
python -m skeleton app doctor --live --json
```

Without `--context-size`, the generated deployment uses an 8,192-token context.
The studio example above explicitly requests 12,288 tokens; supported choices are
4,096, 8,192, 12,288 and 16,384. Larger contexts need more memory, and canonical
activation/capacity checks still apply. Existing installations must match the
requested context and are never rewritten; use a fresh destination when changing it.
The deployment uses two CPU threads, no GPU,
finite execution deadlines and the explicit completion-chat profile. The model
and executable are rehashed by the canonical activation/inference owner. The
provisioning receipt additionally records acquired library digests. The current
runtime independently pins the executable and model; it does not establish a
separate immutable shared-library execution closure.

For another compatible installed GGUF/runtime, use the existing
`python -m skeleton app prepare-local-model --help`. Modern `llama-completion`
chat execution needs `--runtime-profile llama-completion-chat`. Raw completion
remains an explicit alternative. For Qwen3, choose the explicit
`--runtime-profile qwen3-completion-chat` nonthinking template; it preserves
actual messages and binds the template into the runtime profile. The pinned
provisioning recipe selects that model-specific template automatically.
Other CPU architectures require compatible
operator-provided binaries. On a different host preparing assets for a compatible
Linux x86_64 container, explicitly pass `--prepare-for-container`; preparation
does not establish native host execution. The pinned download recipe does not claim native
Windows, macOS or ARM execution.

Hosted execution remains optional: configure the approved provider through the
existing engine environment. Provider credentials stay in the engine process.
The backend and browser do not construct provider clients or load weights.

## Chat, recovery and captured knowledge

Open AI chat after signing in. The model list comes from current canonical
engine inventory, including exact model identity, conservative context limits,
readiness and supported sampling. Automatic selection follows existing routing;
an explicit model choice binds that exact configured pair. Unsupported settings
fail before dispatch.

Each admitted chat turn binds a canonical conversation message to an exact
prepared engine command. Reconnect and resume reuse that command and its
idempotency identity. Actual durable transition events and final receipts drive
the UI. Buffered providers do not produce pretend token streams. A local view
can detach without cancelling work; the explicit stop operation asks the
canonical engine to cancel. Account changes clear derived views and use separate
account-scoped caches. Legacy unscoped browser cache is not imported.

The optional captured-knowledge query searches the signed-in owner's retained
capture sessions. Only actual matching passages enter the context, marked as
untrusted external evidence with exact source and passage digests. Permissions,
consent and source identity are checked again before dispatch, resume and
publication. Captured page instructions do not become system instructions.
Explicit governed memory references retain their original owner, version and
lifetime checks. Attachments and token-level streaming are shown only when the
backend actually supports them.

Erasing a selected capture also blocks a later turn that would reuse its text
through the same conversation history. Start a new conversation with current
permitted context when a source has been withdrawn.

## Capture sources with Dragons

Open `/crawler` and sign in with an account allowed to create captures. The
crawler requires explicit capture consent and acknowledgement of source-use
rights. Select public seed URLs, allowed hosts, a query and finite request,
document, byte, depth and time budgets. Start capture, then run bounded slices
from the app. Pause, resume and cancel use exact versions and operation keys.

Capture uses the existing canonical robots, destination, redirect and transport
policies. The transport preserves inherited proxy and trusted CA configuration.
It does not disable TLS verification or infer a pinned origin peer when an
explicit proxy owns the origin connection. Failed or interrupted transports
retain conservative reserved usage. Browser refresh does not reset the budget.

The queue, counters, failures and events come from committed crawler state.
Sessions retain their complete bounded frontier, robots cache, deduplication,
captured text and provenance in the existing Mongo authority. Recovery resumes
from the last committed snapshot and drains previous physical workers before
reusing capacity. Source inspection and exports stay within the signed-in
owner's consent and source permissions. Truncated event history is labelled.

Cancel stops future acquisition and prevents downstream context reuse. Erase
removes retained request/source text and fences active publication, retaining
only the minimal scoped tombstone and deletion receipt. Previously exported
copies are outside application erasure authority.

Captured material remains **unreviewed**. Acquisition does not grant verified
knowledge status, XP, model-training permission, publication rights or automatic
policy promotion. Dragon Academy's separately reviewed knowledge and practice
store remain separate from these crawler operation snapshots.

## Diagnose a blocked first run

| Observation | Action |
| --- | --- |
| Docker or Compose is missing | Install the host prerequisite, start its daemon, then rerun the installer. |
| Application services are reachable but AI has no model | Provision compatible weights/runtime or configure an approved hosted provider, then recreate the engine. |
| Local activation is invalid | Verify the manifest, exact files, architecture and read-only container paths. Do not set both local model alternatives. |
| Model context is too small | Select a suitable model or reduce the request/output budget; the app never invents a larger context window. |
| Chat or crawler storage admission is unavailable | Check Mongo, the existing engine service identity and tenant/capability grants. |
| Public fetch fails | Inspect committed bounded failures; check the host proxy, CA, DNS, robots policy and target availability. |
| A turn was interrupted | Reopen the canonical conversation and resume its exact prepared turn. Do not create an unrelated duplicate to recover it. |
| A capture was interrupted | Reopen the same session, inspect its state and resume after physical worker recovery. |

Source validators and measured installation/model/crawl workloads are recorded
separately from automated tests. No automated tests were authored or run in this
continuation, following the user's instruction.

For initialized Dragon practice, native SDK/core setup and per-target readiness, see [Studio installation and native readiness](STUDIO_INSTALLATION_AND_NATIVE_READINESS.md).
