# GF-P0 provider runtime recovery: local-native admission and resource custody

**Historical branch:** `feat/gf-c-p0-provider-runtime` (P0-15, P0-16, P0-18).

## Inventory / source reconciliation

- `skeleton/provider_environment.py`, its replay/holdout simulation APIs and
  `tests/test_gf_p0_16_environment_replay.py` already exist on current main
  in a more recent hardened state. They are preserved, not replaced.
- The historical `skeleton/provider_runtime.py` is older and ~9 KB smaller
  than the modern engine-owned provider boundary. Do **not** replace it:
  that would regress tenant/governance controls and newer local-model custody.
- Historical model readiness and resource-envelope gates were missing from
  the current exposed registry. They are adapted as an **opt-in, local-only**
  facade rather than widening the default provider routing or enabling
  cloud providers for Jeeves' initial model.
- The two registry import paths remain byte-for-byte mirrored.

## Operational controls restored

The capability registry ties weight-readiness, rights, usage consent, and
VRAM claims to the **current model attestation revision and digest**.
Every re-registration, deactivation, and reactivation invalidates the grant.
An unknown capacity denies GPU admission; a CPU-only model with a declared
zero GPU requirement can operate without a GPU.

`LocalReadyProviderAdapter` wraps the canonical provider neutral contracts
without duplicating credentials or provider selection. It admits only explicit
local provider identities (local, native, gguf, llama_cpp). Text, stream,
image, speech, variation and edit entrypoints check the current model grant.
An explicit request for a different model is denied, not auto-routed.

`EnvelopedLocalReadyAdapter` adds a finite deadline and bounded generated
text/stream bytes; it cannot bypass the wrapper for remote advisory engines.
It does not assert proof of model content hashes: the native loader must verify
weight bytes, licence grant provenance, tenant policy and executable custody
independently. It does not automatically configure or enable these wrappers.

## Exact-head qualification

- `python -m pytest -q tests/test_gf_model_readiness_reconciled.py`
- `python -m pytest -q tests/test_gf_p0_16_environment_replay.py`
- Existing `skeleton/testing` registry and local-native inference tests.
- Validate both registry mirrors, Pydantic/provider-neutral message schemas,
  local-first model identity, VRAM pressure, partial output, stream cancellation,
  restart re-admission, and no remote provider fallback.
- Include Merge Readiness, Backend Quality, canonical tree source custody,
  secret/malware/workflow/dependency/artifact/hygiene, Windows/GGUF and
  device-backed model tests before approving the PR.

Queued, skipped, cancelled, mocked, outdated-SHA or ancestor checks do not
count as release proof. Do not merge or release based solely on this recovery.
