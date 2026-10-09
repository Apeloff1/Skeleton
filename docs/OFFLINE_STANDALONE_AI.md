# Standalone offline AI: local-model deployment

Skeleton can run text generation with no hosted-model credentials, no Docker,
and no network *service dependency* after its Python application and model
artifacts are installed. This is a local-inference feature, **not** a claim
that the entire crawler, autonomous builder, or all enterprise subsystems
are offline-complete.

## Two supported models

- **Native checkpoint:** `python -m skeleton app local-ai --model ./checkpoint.json
  --prompt "Hello" --max-output-tokens 16 --json`
- **GGUF via a local llama.cpp CLI executable:** `python -m skeleton app local-ai
  --deployment ./deployment.json --prompt "Hello" --max-output-tokens 16 --json`
- **Desktop:** `python -m skeleton app local-ai`; select either **Load
  checkpoint…** or **Load GGUF deployment…**.

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

**Data durability:** The desktop session keeps chat turns in memory only.
Closing the app loses them. There is no implied sync, local persistent
conversation database, managed model download, auto-update or offline
system-completion attestation from this feature.

## Acceptance

```sh
python -m pytest skeleton/testing/test_app_offline_gguf.py -q
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
