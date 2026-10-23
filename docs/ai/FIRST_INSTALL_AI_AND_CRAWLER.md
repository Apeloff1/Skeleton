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

New password, OAuth and bootstrap accounts explicitly belong to the existing
`default` tenant, matching the initial engine service grant. Upgrades preserve
existing user tenants and legacy email-scoped Dragon captures. If a legacy account
receives `crawler_admission_scope_denied`, explicitly include its existing tenant
in the engine attester configuration; do not reassign its stored captures. The
configuration helper supports repeated `--tenant` flags; include `default` too
when retaining access for new default-tenant accounts. Reconfiguration still
requires the helper's original model input and credential-preservation rules.

The first-install continuation has been exercised with fresh Mongo, engine,
production backend and Nginx containers, including actual local-model inference,
account restart recovery and crawler controls. Desktop and mobile browser
operation used the final production web export. Exact results and qualifications
are in [the implementation report](../plan/JEEVES_FIRST_INSTALL_2026-10-15.md).

Use `python -m skeleton app status --live` to check the current service topology
and `python -m skeleton app logs` for service logs. The optional Chroma profile
is not required for bounded lexical retrieval from captured sources.

## Configure existing weights for Compose

The stdlib configuration helper accepts an existing artifact, deployment or
catalog. For a catalog and an explicit administrator:

```bash
python scripts/configure_ai_chat.py --env-file .env.local-catalog \
  --provider local --local-catalog /absolute/models/catalog.json \
  --admin-email operator@example.com \
  --admin-password-file /absolute/private/operator-password.txt
```

For a single GGUF deployment, use `--local-deployment /absolute/local-ai/deployment.json`
instead of `--local-catalog`. The existing `--local-artifact /absolute/local-model.json`
alternative remains supported. Exactly one local input is accepted. The
administrator flags are optional and must be supplied together; public
registration still creates a viewer.

The helper writes a private environment file, a `.compose.json` override and a
`.README.md` with the exact startup command. New configurations include required
persistent master/seal keys and an authenticated backend service grant for
administrator runtime controls. Generated deployment/catalog manifests use
container paths and retain exact weight/executable pins. Original model files
and manifests remain unchanged and are mounted read-only. No inference,
downloads or service startup occurs in this command.

Use the generated README's Compose command with both the repository Compose
file and its generated override. On Linux the engine runs as UID `10001` and
needs read access to model files and execute access to its runtime; the helper
provides targeted access commands and preserves operator file permissions.
Generated nonsecret model manifests use mode `0644`; credentials and the Compose
override use `0600`. Keep all generated private files outside version control.
Intentional `--force` reconfiguration preserves valid existing Mongo credentials
and URLs, signing keys, engine token, persistent master/seal material and
administrator bootstrap. Partial or conflicting credential groups are rejected.
Changing a model does not implicitly rotate those credentials or migrate a
database. A preserved hosted key is reused unless a new key source is supplied.

Portable GGUF executables must be Linux ELF64 for amd64 or arm64. The override
selects the matching container platform, which Docker must support. Adjacent
`lib*.so*` runtime dependencies are bounded to 128 files and 128 MiB per runtime;
the helper does not discover arbitrary system dependencies or establish an
independent shared-library execution pin. Mixed executable architectures in one
catalog are rejected. The engine still performs model activation and resource
admission at startup.

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

### Optional multiple local models

To configure multiple existing local models, set `AI_PROVIDER=local`, leave
`AI_LOCAL_MODEL_PATH` and `AI_LOCAL_DEPLOYMENT_PATH` empty, and set
`AI_LOCAL_MODEL_CATALOG_PATH` to the catalog's engine-visible path, for example
`/app/local-ai/catalog.json` inside the existing read-only local-AI mount. Exactly
one of those three model-path alternatives may be configured. Prepare and mount
the referenced artifacts first; catalog activation does not download them.

A catalog uses this shape; replace both digest placeholders with the SHA256 of
the exact deployment manifest file bytes:

```json
{
  "schema_version": "skeleton.local_model.catalog.v1",
  "primary_model_id": "builder",
  "verifier_model_id": "reviewer",
  "max_total_artifact_bytes": 17179869184,
  "models": [
    {"model_id": "builder", "kind": "deployment", "path": "builder-deployment.json", "sha256": "REPLACE_WITH_MANIFEST_SHA256"},
    {"model_id": "reviewer", "kind": "deployment", "path": "reviewer-deployment.json", "sha256": "REPLACE_WITH_MANIFEST_SHA256"}
  ]
}
```

Paths resolve relative to the catalog. Existing deployment manifests independently
pin model and executable digests. The catalog is limited to 1 MiB and 1–8 unique
model aliases; `verifier_model_id` is optional. Aliases for identical weights do
not establish an independent verifier. The explicit positive byte budget covers
unique referenced files, including manifests, executables and weights; it is
bounded at 1 TiB and does not reserve that amount of RAM. Native JSON artifact
entries additionally require fresh available-memory telemetry and conservative
admission at twelve times serialized artifact bytes plus a 256 MiB reserve.
That estimate is an admission guard, not a resident-memory guarantee. GGUF CLI
deployments retain their existing process, capacity and weight checks.

Recreate the engine after configuring the catalog. Invalid catalogs report
`local_catalog_invalid`; correct the files, digests, budget or activation choice
before retrying. Chat lists exact configured model identities. Runtime optimization
shows each model's own queue, pressure and tenant fairness; serving controls target
the selected model. Selecting a status view does not change the chat's model.

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

## Adaptive runtime and maintenance

For bounded chat/studio/capture starters, local execution limits and recovery from
conflicting or malformed component results, see
[AI workflow foundations and recovery](AI_FOUNDATIONS_AND_RECOVERY.md).

In Jeeves chat, expand the AI conversation status bar to open **Runtime
optimization**. The panel reports current capacity, queue pressure, derived cache,
tenant learning partitions and maintenance tasks. It refreshes while visible and
in the foreground. Account changes clear its observation. Unknown or stale state
does not establish readiness; refresh after restoring the engine connection.

Adaptive local serving is enabled by default. It responds to observed latency,
queueing, failures and resource pressure within the configured static operator
capacity. Its concurrency ceiling cannot increase that capacity. Disabling
adaptive serving disables feedback adjustment; inference remains available under
the configured admission policy.

Tenant outcome learning is also enabled by default. A bounded online MLP learns
from numeric completion, latency and resource outcomes in the existing execution
ledger. Prompts and generated responses are not training data for this learner.
Cold-start and quarantined partitions remain visible. Its predictions guide
operational decisions; correctness, creative quality and ratchet promotion still
require their existing independent evidence. These controls do not train or
promote GGUF/transformer weights, select an unrequested model or implicitly
offload work to an external provider.

**Advanced runtime policy** displays the server's editable fields, units and
bounds for serving, tenant learning and host maintenance. Serving limits are
further constrained by the selected model's installed capacity; a host-wide
change must fit every local route. The form starts from observed values and
submits only your changes. A changed model or policy version requires an explicit
review of the draft. Retention settings govern derived numeric diagnostics;
reducing them can remove retained rows during later bounded cleanup.

Authenticated viewers can inspect state. Only administrators can change policy.
**Serving and maintenance changes affect the entire host; learning changes affect
the current tenant.** Idle maintenance is disabled by default. Enabling it admits
bounded local housekeeping that yields to foreground work. It requires a durable
execution database and is unavailable with an in-memory execution store. Compose
already binds the engine execution database at `/app/data/engine_execution.sqlite`
inside its existing data volume. Preserve that volume to retain versioned policy,
numeric outcomes, learner state and maintenance receipts across restarts.

**Replay adaptation** is a separate default-off maintenance switch. With idle
self-maintenance enabled, it permits bounded extra local predictor updates from
recorded numeric outcomes. It performs no provider work or transformer-weight
training and does not establish game quality.
New canonical outcomes grant only bounded deferred replay credits when their
ordinary replay work was skipped. Idle updates consume those credits; an
unchanged replay buffer does not receive unlimited optimizer updates.

Derived numeric outcome JSON is bounded to 10,000 retained rows per tenant/scope
by default. Idle cleanup also applies a 90-day age limit in chunks of 128 rows.
Small terminal feedback markers preserve exactly-once learning, while immutable
execution results, audit history and cumulative totals remain authoritative.
Legacy overflow catches up in bounded chunks and suppresses extra diagnostic
JSON until capacity is available. Predictor maintenance keeps the newest 2,048
full acknowledged receipts by default; older verified receipts retain small
replay tombstones. Unacknowledged receipts are not discarded to meet that target.

Administrators can open **Numeric learning dataset** to preview and download one
retained page at a time. The default page contains at most 128 candidates; the
API permits up to 256. Select a partition or include untrained outcomes before
fetching. Each accepted row includes twelve normalized features, three operational
targets, usage and exact execution/checkpoint/model/source provenance. Legacy
policy provenance remains explicitly unknown. Invalid rows are omitted with a
reason, so an empty page can still have a next page.

Downloads preserve the opaque server `dataset_json` text, bounded to 1 MiB per
page. **Read next page** uses the returned tenant/filter-bound cursor and a fixed
first-page high-water mark. Retention and late arrivals can still change page
membership: this exports retained diagnostics, rather than an immutable archive
of all past runs. It includes no prompts, answers, tool payloads or provider
credentials and grants no model-training or promotion authority.

Learner readiness also considers actual outcome age. Stale evidence withholds
advice; replay, checkpoint import and maintenance cannot make old observations
fresh. Optimizer health reports measured gradient/update and saturation state.
Persistent stalls can restore the last healthy predictor and require new
canonical outcomes before confidence returns.

Measured studio goals have a separate **Learn numeric control suggestions during
this goal** opt-in. It journals bounded numeric edit observations and predictor
state in the existing scoped goal record, then supplies compatible suggestions
to the planner. Changed source structures and mismatched review protocols do
not become training evidence. Existing review, rollback and export gates remain
authoritative.

**Trim cache** removes eligible derived cache entries; **Clear cache** discards the
derived cache. **Drain new work** stops new admission; **Resume admission** opens
it again. Running work retains its execution ownership and original budgets.
Every command carries the observed policy version. A conflict reloads current
state and requires you to review and reapply the change; commands are never
silently replayed. If a request is unconfirmed, inspect refreshed state before
trying again.
Cache actions retain separate host and model markers so each engine worker can
reconcile intervening commands even when another model receives a later action.
A drained model remains installed and keeps its activation identity. The model
list reports that new work is paused and points to **Resume admission**.

Select a learner partition to inspect prequential error, drift, confidence
constraints, source fingerprints, optimizer work and its last healthy checkpoint.
**Previous learners** and **Next learners** fetch canonical pages of ten partitions;
the panel reports the returned page and total retained count. Confirmed mutations
reload the current page without replaying the action or discarding its receipt.
Prequential loss describes operational prediction error measured before an update;
it does not measure answer correctness or creative quality. Drift, source novelty
and insufficient fresh outcomes withhold learned confidence.

Administrators can **Export checkpoint**, **Import checkpoint**, **Restore last
healthy** or **Reset learner**. JSON files are limited to 256 KiB and contain
bounded numeric predictor/replay state and provenance fingerprints. Import previews
the selected tenant, scope, task, model and feature-schema binding; the engine
validates state and checkpoint digests. Historical source fingerprints remain
provenance. Keep exported files unmodified. Downloads and imports preserve the
original JSON text, including numeric spellings covered by those digests; the
parsed preview is never serialized back into the checkpoint file or import body.
Import, reset and restore require fresh canonical outcomes before
learned guidance resumes. Mutations atomically check both the observed policy
version and learner state version and append an audit receipt. A conflict requires
review and an explicit new action. These files import no policy, grants, execution
results, prompts or transformer weights.

Maintenance reports ownership, physical work, fencing and blocked recovery. Lease
expiry alone does not prove that old work stopped; takeover requires positive
physical-drain evidence. Degraded coordination suspends maintenance and makes its
controls read-only until healthy coordination is observed again.
When a failed task is eligible, **Retry failed task** explicitly requeues its
original continuation under the observed source and attempt count. It grants no
extra model/action allowance and does not immediately execute or repeat verified
optimizer work. Failed acknowledgements retry separately after verified cursor
commit. Result-cache backpressure and unresolved physical custody remain visible.
An eligible **Review circuit reset** action asks you to review the observed failure,
source and generation. It clears only that scope's breaker counters and cooldown.
Task retry/backoff, idle admission and the enabled policy remain in force. Running
or held work and legacy failures without exact bindings cannot be reset. A stale
failure or generation requires refreshing and making a new explicit decision.
Maintenance also reports the age/source of its admission observations and actual
last telemetry. Missing or stale telemetry does not imply idle capacity.

Execution recovery reports aggregate active work and bounded scan progress.
Use one engine coordinator and one engine namespace per execution database;
parallel model workers remain inside that owner. A live OS database lock rejects
a competing coordinator or inherited fork. A persistent namespace pin rejects
incompatible reuse of the same file. Restart recovery reads keyset pages of at
most 128 rows and starts at most 32 recovery drivers concurrently; unchanged
approval/input waiters remain passive, while requested cancellations can recover.

Studio adaptive numeric advice uses **Only this goal** by default. **Remember
compatible goals** permits reuse only when both source and recipient explicitly
opt in and match tenant, principal, project, original baseline/source, review
protocol, reviewer implementation, feature schema and acceptance floors. Current
permissions and original review receipts are checked again. **Start a new shared
history** starts a fresh numeric epoch once that goal has a verified original
baseline; it preserves historical journals and running goals. Retained memory is
bounded to eight provenance goals and 32 observations. It grants no source-text
reuse, quality certification or model-weight promotion.
Issued editor/play/review work can still reconcile after dispatch budgets are
exhausted. A measured regression can expose **Restore incumbent** when the
original restoration/edit/run grants, current source and remaining action
allowance permit it. That explicit action stages an exact host decision through
the ordinary editor gate, without requiring a planner call or inventing a model
receipt. A committed interrupted edit is acknowledged from its exact saved
revision instead of being applied again.

This runtime implementation is a construction draft, not enterprise certification.
No automated tests were authored or run for this build, following the user's
instruction; compilation alone does not establish production quality.

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

In the source library, withdraw an individual capture or set its permitted
capture age between 60 seconds and 24 hours. Owners can withdraw; editor/admin
authority is required to restore use or change the age limit. Saved changes use
the session version and an exact operation key. Conflicts require an explicit
refresh/reapply. Withdrawing a source removes it from text/context/search/export
and invalidates queued and reviewed references against the older policy version.
Restoring it requires a new review before an older reference can be reused.
Freshness is measured from capture time and consent expiry; the app does not
claim to have rechecked the remote page. These controls do not recrawl a source.

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
