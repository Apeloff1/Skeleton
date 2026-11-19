# Air-gapped local Jeeves: four-image Docker archive

**Status:** source-level review-only workflow. Complements the canonical opt-in
local AI Docker operator, exact-GGUF model backup and application cold-byte
backup. This command does **not** import an image, make the application run, or
certify guarded chat. No service or named Docker volume is modified.

## Offline transport and trust boundaries

A stand-alone deployment needs all of the following separate artifact classes:

1. Four canonical Docker images: Mongo, Skeleton local Jeeves engine, backend,
   and frontend. They must already exist in the exporting host's Docker daemon.
2. Operator-supplied, properly licensed GGUF plus exactly matched llama.cpp
   executable and pinned adjacent libraries (backup-model,
   verify-model-backup, restore-model-backup).
3. Application state if retaining existing conversations/projects
   (recovery-preflight, cold-backup-app). Current cold copy preserves bytes,
   not a transactionally consistent multi-store restore.
4. Private first-install credentials/configuration, separately provisioned
   on the destination. These must not be copied into image archives.
5. Independent hardware/architecture, protected inference, operational
   recovery, security and release verification.

The archive never embeds GGUF, model manifests, credentials, local .env,
MongoDB volumes, SQLite data, a source repository or database state.

## Operator commands

Run after installing and locally building the complete selected CPU, NVIDIA or
ROCm Compose stack on the **exporting** machine. Use a preexisting,
operator-owned private 0700 parent; the archive destination must not exist.

    python scripts/local_ai_docker.py --mode cpu doctor
    python scripts/local_ai_docker.py --mode cpu build
    python scripts/local_ai_docker.py --mode cpu image-inventory
    python scripts/local_ai_docker.py --mode cpu export-images \
      --destination /home/operator/private-images/images-001

On any machine with this Python source and the archived bytes, independently
verify without a running Docker daemon:

    python scripts/local_ai_docker.py verify-image-bundle \
      --directory /home/operator/private-images/images-001

For a GPU build, replace --mode cpu with --mode nvidia or --mode rocm
**only for inventory/export**. Verification uses the archived mode in its
sealed receipt. Do not claim CPU images have been tested on GPU or vice versa.

The export runs docker image inspect for each of the four local references,
then docker image save --output ... sha256:<exact-id> for each. Reinspection
requires unchanged source references. Every archive is hashed with SHA-256,
checked for exactly one Docker-save image, no unsafe paths or link members,
bounded entries/bytes, and a config JSON whose SHA-256 equals the immutable
Docker image ID. An independent offline verifier rehashes **all four complete
archives**, reopens them, and checks every recorded result and the receipt
digest. Its directory listing must contain exactly four named .tar files
and the final receipt. Partial/failed exports have no completed receipt, are
preserved privately and cannot be treated as verified.

There is intentionally **no** docker image load, automatic retag, push,
pull, build, extraction, container start, or import step in this wave.
Docker-save archives may contain source RepoTags. Loading unknown source tags
could repoint the destination host's existing local tags. An independently
reviewed tag collision/host-platform policy and a source authorization
procedure are required before any future import is enabled.

## Evidence and acceptance limits

- **Source-only:** tests exercise Docker command admission, immutable image
  inventory, synthetic tar/config digests, receipt tampering, truncation,
  symlinks, duplicate members, missing layers and changed image references.
- **Physical exporting host:** requires all four images actually built and
  present; archive export/rehash has to succeed with the real daemon. Synthetic
  generated archives are not physical Docker qualification.
- **Destination:** must independently attest OS/architecture, image/runtime
  ABI, compatible accelerator driver/device, all independent image digests,
  source tags, bind paths, credentials, Compose topology, image imports and
  subsequent live runtime checks. This is **not yet implemented**.
- **Application:** backend provider endpoint or a standalone GGUF turn cannot
  grant protected Jeeves chat. Active-GGUF tokenizer attestation, independent
  bounded reviewer, source epoch writer fencing, actor migration, and live
  guarded end-to-end inference remain required.
- **Persistence:** a copied Mongo or SQLite volume is not proof of writer
  quiescence, cross-store atomicity, read consistency or recoverability.
- **Release:** an unsigned SHA-256 receipt detects accidental corruption but
  does **not** authenticate an untrusted exporter or provide signing,
  provenance or a reproducible build claim.

The new archive is an **additional offline-transport artifact**, not a
substitute for the separate model, application, device and release holds.
