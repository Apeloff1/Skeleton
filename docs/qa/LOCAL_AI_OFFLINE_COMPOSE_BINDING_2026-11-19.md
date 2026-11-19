# Offline Jeeves Docker: immutable-ID Compose binding

**Scope:** review-only implementation stacked after offline image transport and
the canonical local-first Jeeves Docker runtime. Not an alternate model service,
release, import, tag switch or container launcher.

## Gap closed

Tag-neutral offline imports intentionally create **untagged** local images.
Canonical Compose references Mongo by a pinned registry name and the
application images by local tags. Imported bytes alone cannot make those names
resolve on an air-gapped host. An operator must not manually retag arbitrary
images, weaken the Mongo digest pin, mutate credentials, or enable pulls.

This wave binds four exact verified Docker **image IDs** using a new, private,
create-only Compose overlay. Every original Compose file, model mount, secret,
database volume, API URL, service dependency, security option and GPU resource
profile is preserved. The separate overlay contains exactly four image
references and no credentials.

## Trust chain

- All four archived images are independently verified; the expected complete
  receipt-file SHA-256 is supplied through a trusted out-of-band channel.
- Every pinned sha256:<64 hex> image ID must already be physically present in
  the destination Docker daemon. The plan never pulls, tags, imports or builds.
- The Docker engine platform must match the complete archived Linux/amd64 or
  Linux/arm64 image set. GPU/WSL2 still require independent device evidence.
- The canonical CPU/NVIDIA/ROCm Compose configuration must render and satisfy
  its existing full deployment security boundary: loopback-only ingress,
  authenticated internal Mongo, correct engine/browser/backend destinations,
  the read-only GGUF mount, dropped capabilities, no hosted providers, known
  GPU device allocation, and canonical named volumes.
- The overlay contains precisely four services.<role>.image fields, all set to
  admitted immutable image IDs. It never changes volumes, networks, ports,
  environment, build settings, restarts, security options or profiles.
- Docker Compose must render the complete multi-file configuration as exactly
  the independently admitted base JSON with only those four image fields
  changed. Any non-image drift fails closed.
- Verification reads the owner-only sealed artifact with O_NOFOLLOW,
  independently checks SHA-256 and permissions, recomputes source admission,
  confirms local image IDs, and runs the actual Compose parser again.

## Operator commands

Install Docker Engine and Compose locally; run the canonical first-install
setup to provision a private .env and model directory. Separately verify and
import all four images before binding them. Choose the same mode used for
the archive (cpu, nvidia or rocm).

Read-only admission (no writes):

    python scripts/local_ai_docker.py --mode cpu plan-offline-compose \
      --directory /home/operator/private-offline-ai/transfer-001 \
      --expected-receipt-sha256 INDEPENDENT_64_HEX_DIGEST

Create a new private binding. The destination must not exist, and its
operator-owned parent must already be 0700:

    install -d -m 0700 "$HOME/private-offline-ai/bindings"

    python scripts/local_ai_docker.py --mode cpu prepare-offline-compose \
      --directory /home/operator/private-offline-ai/transfer-001 \
      --expected-receipt-sha256 INDEPENDENT_64_HEX_DIGEST \
      --destination "$HOME/private-offline-ai/bindings/local-cpu-001"

Independently revalidate bytes, actual stored IDs, and merged Compose:

    python scripts/local_ai_docker.py --mode cpu verify-offline-compose \
      --directory /home/operator/private-offline-ai/transfer-001 \
      --expected-receipt-sha256 INDEPENDENT_64_HEX_DIGEST \
      --overlay-directory "$HOME/private-offline-ai/bindings/local-cpu-001"

The generated directory contains precisely two owner-private files:

- docker-compose.offline-image-ids.yml — a JSON-form YAML subset accepted by
  Docker Compose; four exact sha256 image IDs, no secrets.
- offline-compose-binding.receipt.json — trusted source fingerprint, image ID
  list, mode, platform, project, overlay hash and explicit FALSE claims for
  runtime startup, chat qualification, epochs, recovery and release.

The receipt is created **last**, only after a successful real multi-file
Compose render. A failed write leaves an unqualified private partial
directory; no overwrite, rollback, tag removal, volume delete, pruning, or
application startup is attempted.

## No-pull boundary

The normal operator's existing up action performs offline GGUF model
preflight, actual local generation and guarded app checks before declaring
readiness. This wave does **not** add an offline-up action and is not proof
that the protected Jeeves chat can become operational.

A future independently reviewed launcher must consume this overlay, use
--no-build and --pull never, repeat the exact image/model/runtime attestation
and refuse readiness until the backend and engine independently qualify the
protected local inference flow. Manual ad-hoc docker compose up is not a
substitute for these gates.

## Physical qualification

CI exercises a separately scoped, real Docker Compose parser. It creates
disposable JSON-as-YAML files with four synthetic sha256 image IDs, runs
docker compose config --format json and compares the entire rendered
configuration against exactly four allowed image-field replacements.
It then injects a hostile privileged=true override to prove that unrelated
privilege drift is visible and denied by the comparison.

The probe never starts containers, builds, pulls or loads images, uses
production Docker volumes, accesses credentials, or executes GGUF inference.

The focused regression suite exercises exact structured equality, private
artifact creation, independent re-attestation, forged receipts, missing
images, model-mode mismatch, malformed source metadata, symlink/unlisted
artifact rejection, partial failures, no-up guarantees, and environment/
port/volume/network/build/security drift.

## Open release holds

1. Production four-image import and controlled --pull never startup under
   physical CPU/GPU resource constraints.
2. Actual licensed GGUF native inference, tokenizer custody and offload.
3. Independently administered bounded reviewer and guarded Jeeves
   application prompt/response authorization.
4. Majority-durable shared Mongo writer epochs, migration/quiescence and
   external writer isolation.
5. Coherent full application backup/restore and restarted state recovery.
6. Windows 11/WSL2, driver/ABI, resource pressure, crash/restart tests.
7. Exact-head security, native, device and signed release provenance.

The stacked PRs remain review-only; no merge, release or guarded chat
qualification is claimed from successful image-ID configuration.
