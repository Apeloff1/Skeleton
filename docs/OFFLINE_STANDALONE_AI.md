# Standalone offline AI: local-model deployment

Skeleton can run text generation with no hosted-model credentials, no Docker,
and no network *service dependency* after its Python application and model
artifacts are installed. This is a local-inference feature, **not** a claim
that the entire crawler, autonomous builder, or all enterprise subsystems
are offline-complete.

## Build a portable offline installation kit

Build an application wheelhouse on a **connected build machine** matching the
destination operating system, architecture, and Python minor version:

```sh
python -m pip wheel --wheel-dir ./offline-wheels ".[local-inference]"
python scripts/offline_kit.py pack --wheels ./offline-wheels \
    --destination ./Skeleton-Offline-Kit
python scripts/offline_kit.py verify --kit ./Skeleton-Offline-Kit
```

To include a separately licensed GGUF model and a locally trusted llama.cpp
CLI binary, add `--gguf ./weights.gguf --llama ./llama-cli --model-id my-local-model`
to the `pack` command. The kit copies and hashes both artifacts, and
generates the runtime deployment manifest. It does **not** download models
or pretend a synthetic fixture is a trained AI.

Move the verified kit using trusted local media. On the **disconnected**
destination with a compatible Python 3 interpreter, run:

```sh
python offline_kit.py verify --kit .
python offline_kit.py install --kit . --destination ../Skeleton-Offline
../Skeleton-Offline/bin/python -m skeleton app local-ai
```

On Windows, replace `bin/python` with `Scripts\\python.exe`. The installer creates
a Python virtual environment, resolves packages strictly from the wheelhouse
using `pip --isolated install --no-index --only-binary`, and does not
fetch packages or weights. If model artifacts are included, the model manifest
will be at `../Skeleton-Offline/offline_model/model/deployment.json`.
Select that manifest in the desktop window or use
`--deployment` in the headless CLI.

**Important limits:** This is a genuinely no-index installation workflow,
not yet a self-contained Windows executable for the *whole* product. Python,
OS runtimes (such as Windows DLLs or GPU drivers), and the installed local
model's native library dependencies must be available on the machine in
advance. A wheelhouse produced for Linux will not work on Windows; a wheel
set for one Python version is not automatically portable to another.
The manifest provides SHA-256 corruption detection, **not a cryptographic
release signature or provenance guarantee**. Independently verify the
distribution source before using it.


## Self-contained Windows offline console

The Windows installer builds two frozen, Python-bundled executables:

- `Skeleton.exe` — the existing graphical setup/runtime launcher, including
  its **Local AI (offline)** button.
- `SkeletonOffline.exe` — a separate **console** executable for headless,
  credential-free local inference. It does not require system Python or Docker.

Example in PowerShell with a trusted local model already installed:

```powershell
.\SkeletonOffline.exe --native-smoke
.\SkeletonOffline.exe --deployment .\model\deployment.json --prompt "Hello" --json
.\SkeletonOffline.exe --deployment .\model\deployment.json --prompt "Continue" --workspace .\state\chats.sqlite --session-id default --json
```

`--native-smoke` only proves the packaged native inference graph can execute
using a tiny deterministic test fixture; it is not a trained assistant and
does not validate real GGUF/model quality. The Windows installer workflow
now checks both installed executables after silent installation.

The wheelhouse kit below is a separate, Python-dependent distribution route
for matching operating systems and Python versions. A Windows frozen console
does **not** include arbitrary local GGUF weights or automatically install
GPU drivers or the llama.cpp executable.

## Entirely local document knowledge library

The desktop includes **Open local library…**, **Index text folder…**
and **Search local library**. This is a local SQLite FTS5 projection of
user-selected documents. It works with no model loaded and does not require
Docker, a database server, an internet connection, or provider credentials.

The frozen console, installed `skeleton-offline` command, and unified app
CLI can build or search exactly the same local SQLite index:

```sh
skeleton-offline --library ./knowledge.sqlite --index-dir ./notes --json
skeleton-offline --library ./knowledge.sqlite --search "game physics" --json
python -m skeleton app local-ai --library ./knowledge.sqlite --search "physics" --json
```

To explicitly enrich a **real local model inference** with retrieved text:

```sh
skeleton-offline --deployment ./deployment.json --prompt "Explain physics" \
  --library ./knowledge.sqlite --use-library --context-limit 3 --json
```

Results include relative paths, SHA-256 checksums and bounded excerpts.
The model response's `retrieved_sources` field identifies supplied local
references; it does not prove that the answer is correct or faithful. Source
text is clearly marked untrusted. Document data never becomes permission for
code execution, tool use or a hosted-model request.

The importer reads only regular UTF-8 text files with these extensions:
`.txt`, `.md`, `.markdown`, `.rst`, `.py`, `.json`,
`.jsonl`, `.csv`, `.toml`, `.yaml`, `.yml`.
It rejects symlinks, embedded NUL bytes and files over 128 KiB. Each batch
is bounded to 2,000 files and 32 MiB. The accumulated knowledge
index is bounded to 10,000 documents and 128 MiB of source text. Indexing is transactional, supports
incremental replacement and prunes deleted files **within the selected
directory**, without deleting content from other indexed roots. Search
identifiers are parameterized and all returned text is checked against its
stored SHA-256. Neither PDFs nor arbitrary binary formats are opened by this
low-trust local text importer.

This is an **opt-in local search utility**, not the canonical crawler or
semantic knowledgebase owner. Indexes and conversation databases are
unencrypted local files. Use filesystem permissions/encrypted volumes for
private knowledge. A normal local application cannot guarantee that a
malicious operating-system process or third-party model executable has no
network access; enforce that separately at the OS level.

## Restart-safe on-device knowledge acquisition

Local folders can now be submitted to a durable bounded indexing queue.
This remains an explicitly requested **local file-indexing job**, not
unattended internet crawling or autonomous source promotion.

```sh
skeleton-offline --queue-db ./index-jobs.sqlite \
  --enqueue-dir ./notes --queue-library ./knowledge.sqlite --json
skeleton-offline --queue-db ./index-jobs.sqlite \
  --run-queue --drain-limit 5 --queue-status --json
```

The queue is SQLite-backed, reopens after process restarts, and admits only
the existing no-network local text indexer. Jobs are identified by opaque
tokens and atomically claimed under a 15-minute lease. A stale worker may
not replace the newer job receipt, and workers can recover from an expired
lease up to a bounded three-attempt budget. Processing always happens in
the foreground when `--run-queue` is invoked; there is no hidden always-on
daemon, timer or hosted worker. Unavailable folders produce a bounded
retryable failure rather than a fabricated success.

Operators can inspect `--queue-status`, cancel an unstarted job with
`--cancel-queue-job <id>`, or explicitly requeue a terminal failure with
`--retry-queue-job <id>`. If a host requires recurring scans, use its
trusted operating-system scheduler to invoke a bounded queue run.

For the detailed finding-by-finding threat review, repaired attack paths,
regression mapping and release-signoff conditions, see
[Offline Standalone Adversarial Review](OFFLINE_STANDALONE_ADVERSARIAL_REVIEW.md).
It is a review ledger, **not** a claim that exact-head CI or air-gapped
real-model acceptance has passed.

## Deep local state integrity audit

Use the standalone console to inspect the semantic correctness of local
chat, knowledge and queue databases without invoking a model, network
access or repairing the data implicitly:

```sh
skeleton-offline --audit-workspace ./chat.sqlite \
  --audit-library ./knowledge.sqlite \
  --audit-queue ./index-jobs.sqlite --json
```

The desktop also offers **Audit local state**, which verifies an attached
conversation workspace and/or local knowledge index on a background worker.
The audit checks transcript checksums and complete turns, source text hash
and FTS5 projection consistency, and indexing job leases and result records.
It is read-only and requires existing database paths. It intentionally does
not treat a valid checksum as authentication or a trustworthy model answer.

A damaged search index is not silently promoted into a valid backup. After
verifying that the original source folder is trustworthy and unchanged,
explicitly run **Index text folder…** or
`skeleton-offline --library ./knowledge.sqlite --index-dir ./notes`
to rebuild mismatched FTS5 entries and prune orphaned search rows. Then
rerun the audit. Chat transcript corruption or forged queue results must
be recovered from independently verified snapshots; do not automatically
fabricate missing turns or signed evidence.

New local chat and document databases use owner-only permissions on POSIX
systems. Existing database permissions are left unchanged. On Windows,
configure NTFS access control and encryption according to the device's
security policy.

## Portable database recovery

Conversation workspaces, local document libraries and indexing queues can
be snapshotted to an operator-selected folder using SQLite's online
backup API. This captures committed WAL pages instead of byte-copying
live, possibly inconsistent database files.

```sh
skeleton-offline --snapshot-to ./offline-recovery \
  --snapshot-workspace ./chat.sqlite \
  --snapshot-library ./knowledge.sqlite \
  --snapshot-queue ./index-jobs.sqlite --json
skeleton-offline --verify-snapshot ./offline-recovery --json
skeleton-offline --restore-from ./offline-recovery \
  --snapshot-workspace ./new-chat.sqlite \
  --snapshot-library ./new-knowledge.sqlite \
  --snapshot-queue ./new-index-jobs.sqlite --json
```

Restore requires **new destination files** and validates every database
schema, SQLite integrity check, file size and SHA-256 checksum before
publishing the restored files. Existing user databases are never
intentionally overwritten. No network or cloud account is involved.

**Boundaries:** Each database receives a consistent SQLite online backup,
but the collection is **not a single globally atomic snapshot** across all
three subsystems. Stop writers when cross-database synchronization matters.
The snapshot is **plaintext** and is not signed or encrypted. A SHA-256
manifest detects corruption, but an actor controlling both manifest and
database files can forge it. Independently authenticate and protect
backups on trusted media. Restored transcripts remain context, not
execution authorizations or canonical production conversation state.

## Opt-in Windows outbound blocking

An optional local script manages narrowly scoped Windows Defender Firewall
outbound-block rules for the installed offline console and, optionally,
the separately installed llama.cpp executable. It is **never invoked
automatically during installation** and does not change the machine's
global firewall profile.

Run an elevated PowerShell console only after independently verifying the
executable paths and source of the policy script:

```powershell
.\\scripts\\windows\\offline_network_policy.ps1 -Mode Apply -OfflineExe "C:\\Path\\SkeletonOffline.exe" -LlamaCli "C:\\Models\\llama-cli.exe"
.\\scripts\\windows\\offline_network_policy.ps1 -Mode Status -OfflineExe "C:\\Path\\SkeletonOffline.exe" -LlamaCli "C:\\Models\\llama-cli.exe"
.\\scripts\\windows\\offline_network_policy.ps1 -Mode Remove -OfflineExe "C:\\Path\\SkeletonOffline.exe" -LlamaCli "C:\\Models\\llama-cli.exe"
```

The script uses path-derived rule identifiers, refuses preexisting rules
associated with a different application path, and removes only the exact
selected rules when expressly requested. `Status` is read-only and
returns a nonzero exit code when any selected application block is missing.
The status JSON explicitly records `host_isolation_proven: false`.

**Limitations:** These Windows Firewall rules restrict outgoing traffic
for the named executables. They do not air-gap the host, isolate separate
programs, block all IPC or protect against privileged malware or operating
system compromise. Other processes and any additional spawned binaries
must be governed separately. For a truly disconnected acceptance test,
use an independent OS policy or physically isolated test machine.

## Original synthetic training set and evaluation

The first fully materialized offline training curriculum now lives at
\`skeleton/ai/training/datasets/offline_foundations_v1/\` and includes
720 deterministic instruction/answer examples across 12 game-engine,
reasoning, local-security and text-processing task families. The train
split has 504 examples; validation and test each have 108. A dedicated
\`train_corpus.txt\` exposes **training data only**, and its provenance,
source rights, SHA-256 digests, and group-disjoint allocation are pinned
in \`manifest.json\`.

See [Offline Synthetic Training Dataset](OFFLINE_SYNTHETIC_TRAINING_DATASET.md)
for full schema, independent regeneration, data rights, held-out scoring,
failure-injection tests, and the experimental local-model training path.
This set does **not** imply that a trained general-purpose model exists,
that external game assets may be used for training, or that candidate
weights are approved for deployment.

## Functional model qualification with real local inference

Artifact readiness and the tiny `--native-smoke` check are not sufficient
to qualify a device for real offline chat. Use `--qualify-model` with your
locally installed checkpoint or GGUF deployment, after independently
verifying its publisher and model license:

```sh
skeleton-offline --deployment ./deployment.json --qualify-model --max-output-tokens 16 --json
skeleton-offline --model ./checkpoint.json --qualify-model --max-output-tokens 2 --json
python -m skeleton app local-ai --deployment ./deployment.json --qualify-model --max-output-tokens 16 --json
```

The qualification makes **two actual inference calls** using the supplied
model, closes the first model/session and its SQLite connection, reopens
the same model and locally stored conversation context, and verifies the
second committed turn and pinned model/runtime hashes. It reports model
identity, output hashes, per-turn execution receipts and token counts;
neither generated answers nor transcript text are written to stdout.
Temporary user context is deleted at the end. This is **session reopen
inside one process**, not a subprocess reboot, power-loss recovery, real
model quality benchmark or OS-enforced airgap.

The report explicitly sets
`network_isolation_verified=false`,
`trained_model_quality_verified=false`, and
`release_signed=false`. A simulated llama.cpp CLI can pass this interface
contract without containing a useful trained model, so successful
qualification of a real deployment needs independently trusted weights,
a genuine executable and target-hardware observation.

The Windows installer workflow creates a temporary **synthetic**
deterministic native checkpoint during CI and runs the above two-turn check
using the *installed frozen SkeletonOffline.exe*. It tests executable
packaging, model inference integration, SQLite recovery and receipt
generation without requiring system Python for the installed application.
This is not a claim that production trained weights are bundled.

## Offline readiness doctor

Use `--doctor` with one preinstalled local artifact before running it:

```sh
skeleton-offline --deployment ./model/deployment.json --doctor --json
python -m skeleton app local-ai --model ./checkpoint.json --doctor --json
```

The doctor checks the exact local checkpoint identity or the SHA-256-pinned
GGUF plus llama.cpp executable and reports the inspected hashes. It does not
run a model, contact a provider, prove device library compatibility, evaluate
model intelligence, or attest to operating-system egress isolation. These
distinct statuses appear explicitly in its JSON response to prevent false
standalone qualification.

## Local SQLite conversation workspace

In the desktop app, load a native checkpoint or GGUF deployment, then
choose **Attach local workspace…** to select or create a local SQLite file.
The existing conversation must be empty before attaching. Previously saved
turns for the same model are restored into the desktop view. The **New
conversation** action asks for confirmation before clearing the currently
bound durable transcript. Model switches close the old workspace connection.

For automatic headless transcript persistence, pass `--workspace` and an
explicit `--session-id` (defaults to `default`). Both `skeleton-offline`
and `python -m skeleton app local-ai` can use this feature:

```sh
skeleton-offline --deployment ./deployment.json --prompt "First" \
    --workspace ./chat.sqlite --session-id my-session --json
skeleton-offline --deployment ./deployment.json --prompt "Second" \
    --workspace ./chat.sqlite --session-id my-session --json
```

The local SQLite store commits only complete, checksum-bound turns and uses
optimistic revisions to prevent concurrent writers from silently replacing
each other's history. It rejects another model's identity and corrupted
transcripts. An interrupted or rejected generation is not committed to
workspace state. History is intentionally bounded to eight recent full
turns to constrain model context. The database is **unencrypted** user data
and remains separate from the production conversation authority. Protect it
with OS permissions and encrypted storage where appropriate.

Manual `--backup-in` cannot be combined with a revisioned workspace,
because that would ambiguously overwrite workspace history. Manual
`--backup-out` can export a snapshot after successful inference.

## Two supported models

- **Native checkpoint:** `python -m skeleton app local-ai --model ./checkpoint.json
  --prompt "Hello" --max-output-tokens 16 --json`
- **GGUF via a local llama.cpp CLI executable:** `python -m skeleton app local-ai
  --deployment ./deployment.json --prompt "Hello" --max-output-tokens 16 --json`
- **Desktop:** `python -m skeleton app local-ai`; select either **Load
  checkpoint…** or **Load GGUF deployment…**.

## Portable offline conversation recovery

The desktop now provides **Back up conversation…** and **Restore
conversation…** after a native checkpoint or GGUF deployment is loaded.
Backups are explicit user-owned JSON files and are **not** silently synced or
used as the server-side authoritative conversation database. A restored
transcript is treated as untrusted local model context, never a verified
execution receipt. Restoring requires an empty conversation (choose New
conversation before restoring into an active session).

The headless CLI supports copying local chat context across processes:

```sh
python -m skeleton app local-ai --deployment ./deployment.json \
    --prompt "First turn" --backup-out ./my-chat.json --json
python -m skeleton app local-ai --deployment ./deployment.json \
    --prompt "Continue the conversation" \
    --backup-in ./my-chat.json --backup-out ./my-chat.json --json
```

Backup files contain **plaintext** conversation content. Keep them on an
access-controlled local volume, encrypt the storage if appropriate, and remove
the files when no longer needed. The writer atomically replaces the selected
backup, uses private permissions on POSIX, limits file size and message counts,
and pins the full backup to a local model SHA-256. A checksum detects accidental
corruption; it does not provide signing, authentication or protection against
a malicious actor who can rewrite both the backup and its checksum. No cloud
account or hosted provider is involved.

GGUF deployment uses the canonical `skeleton.ai.runtime.inference` engine;
it does not route through remote provider clients. Headless responses contain
model identity, token usage and the execution receipt digest. Both options
require genuine operator-supplied weights; the application does not bundle
a trained model or silently substitute a demo/retrieval response.

## Offline GGUF manifest

Create a JSON manifest next to the already-installed runtime and model:

```json
{
  "schema_version": "skeleton.local_model.deployment.v1",
  "runtime_kind": "llama.cpp-cli",
  "model_id": "my-local-model",
  "executable_path": "bin/llama-cli",
  "executable_sha256": "REPLACE_WITH_64_LOWERCASE_HEX_SHA256",
  "model_path": "models/model.gguf",
  "model_sha256": "REPLACE_WITH_64_LOWERCASE_HEX_SHA256",
  "config": {
    "timeout_seconds": 120,
    "context_size": 2048,
    "threads": 4,
    "gpu_layers": 0,
    "temperature": 0
  }
}
```

All paths are resolved relative to the manifest. SHA-256 values can be
generated locally with `sha256sum bin/llama-cli models/model.gguf` (Linux)
or `Get-FileHash -Algorithm SHA256` (PowerShell). Copy the manifest, llama.cpp
binary and GGUF to the destination machine using trusted offline media.
Install any operating-system/accelerator libraries required by the *chosen*
llama.cpp binary separately. Never add copyrighted/third-party model
weights to the repository without their redistribution rights.

## Trust and failure semantics

- The deployment loader rejects missing files, a malformed GGUF header,
  unrecognized manifest fields, symlinked model paths, and SHA-256 mismatches.
- The app hashes both local artifacts on each GGUF execution. Changes
  after the model was loaded fail closed. No cached fake answer is used.
- Only an admitted text result with a bound local execution receipt enters
  the in-memory conversation. Tool requests, partial failures and
  cancellations do not silently become chat history.
- Message size, output token budget and conversation history are bounded.
- The app sends neither prompts nor model weights to a hosted provider; the
  llama.cpp adapter removes provider credentials and proxy variables from its
  child environment and forbids remote-acquisition options.

**Security boundary:** The no-network design removes application-level cloud
dependencies; it is not OS-level network isolation for an arbitrary binary.
Use an independently verified, trusted llama.cpp build and disable outbound
network access using the OS firewall/sandbox for an air-gapped guarantee.
Do not run unknown binaries just because their digest matches a manifest.

**Data durability:** Desktop turns remain in memory unless manually backed up
or explicitly attached to a local SQLite workspace. The headless CLI also
supports opt-in automatic local SQLite persistence. Neither backup format nor workspace is the production authoritative
conversation database. Managed downloads, updates, encrypted local state,
and offline system-completion attestation are not yet provided.

## Acceptance

```sh
python -m pytest skeleton/testing/test_app_offline_gguf.py skeleton/testing/test_offline_history_backup.py skeleton/testing/test_offline_kit.py skeleton/testing/test_offline_console.py skeleton/testing/test_offline_workspace.py skeleton/testing/test_offline_readiness.py skeleton/testing/test_offline_library.py skeleton/testing/test_offline_index_queue.py skeleton/testing/test_offline_snapshot.py skeleton/testing/test_offline_audit.py -q
python -m pytest skeleton/testing/test_local_model_deployment.py -q
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
python scripts/check_provider_bootstrap.py
python scripts/check_enterprise_ai_superiority.py --json
python scripts/check_enterprise_ai_implementation_notes.py --json
```

These checks verify contracts and representative local model fixtures, not
a real GGUF weight distribution. Genuine-device qualification requires a
locally licensed model, host-specific llama.cpp dependencies, a cold-start
and an OS-enforced offline acceptance test.
