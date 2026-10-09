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

On Windows, replace `bin/python` with `Scriptspython.exe`. The installer creates
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

**Data durability:** Live turns remain in memory unless the user explicitly
exports a portable backup. The app does not yet provide automatic durable
history, a local authoritative conversation database, managed model downloads,
auto-update or offline system-completion attestation.

## Acceptance

```sh
python -m pytest skeleton/testing/test_app_offline_gguf.py skeleton/testing/test_offline_history_backup.py skeleton/testing/test_offline_kit.py -q
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
