# Offline Docker local AI: authenticated-byte transport and tagless image staging

**Scope:** review-only source candidate layered on the canonical local-only
Jeeves Docker operator. This is not a new AI backend, model provider or
unconditional Docker installer. It never weakens protected chat policy.

## Deployment architecture

The deployment is divided into independently verified planes.

| Plane | Artifact | Authority |
|---|---|---|
| Runtime images | Four locally built/pinned Docker images | This image bundle, imported by immutable image ID |
| Model | Licensed GGUF, matching pinned Linux llama.cpp executable and libraries | Existing model backup/restore and Jeeves deployment pin |
| Data | Mongo, backend SQLite, engine SQLite and optional Chroma | Existing read-only recovery inventory and non-atomic cold byte copy |
| Credentials | Existing first-install secrets and local service tokens | Local operator setup; NEVER included in images or archive |
| Protected chat | Active tokenizer, bounded independent reviewer, tenant/source epoch | Canonical engine/backend guards; not satisfied by image import |
| Device | CPU memory, GPU backend/driver and WSL2 runtime evidence | Independent physical qualification, not a Compose render |
| Release | Reviewed dependency pins, image provenance and signing | Independent release gate, not a self-hashed receipt |

This continuation adds stronger **offline transport and staging**, not another
model runner. Model inference remains entirely in the Skeleton engine.
No container has to be running for archive verification.

## Trust model and constraints

A Docker save archive may carry repository tags. A direct Docker load could
silently replace a destination tag with a foreign image, including one used by
an unrelated application. The export tool therefore repacks the Docker save
archive: it removes any legacy repositories index and sets the sole
manifest.json RepoTags list to empty before sealing the bytes. Layer contents
and the exact image config are copied without decoding or extraction.

A receiver must supply the SHA-256 of the **complete receipt file** from a
separate trusted channel when planning or staging an import. The digest
embedded inside the receipt provides only tamper evidence, not authentication.
If an adversary controls both files and the independently supplied expected
digest, the checksum cannot authenticate provenance.

The verifier enforces:

- Exactly one source image per archived tar and exactly four roles:
  mongo, skeleton, backend, frontend.
- Exact binary Docker config digest equal to the image ID.
- SHA-256 of every uncompressed saved layer equal to its ordered rootfs diffID.
- No Docker source tags, legacy repositories index, symlinks, hardlinks,
  special archive entries, duplicate paths, traversal or undeclared files.
- Explicit per-tar and aggregate size ceilings and a finite count of entries.
- Identical Linux/amd64 or Linux/arm64 architecture across all four images.
- Owner-only 0700 archive root and 0600 files.
- Exact mode match between exporter and importer: CPU, NVIDIA or ROCm.
- Exact destination daemon OSType/Architecture match before loading.
- No registry pulls, image tags, container starts, GPU assumptions, model
  downloads, secret access or persistent volume mutation.

The source Docker image reference remains recorded in the receipt for
audit, but it is not applied on the destination daemon.

## Export, offline verification and transport

The exporter must already have four local images. Building them is a separate
explicit step. A shell creating an archive parent must grant only the operator
read/write/traverse permission.

    install -d -m 0700 "$HOME/private-offline-ai"

    python scripts/local_ai_docker.py --mode cpu doctor
    python scripts/local_ai_docker.py --mode cpu build
    python scripts/local_ai_docker.py --mode cpu image-inventory
    python scripts/local_ai_docker.py --mode cpu export-images \
      --destination "$HOME/private-offline-ai/transfer-001"

Do not use an existing destination. A failed export leaves a partial private
archive with no qualified final receipt. It never overwrites user data.
A Docker image save is local and never downloads a replacement image.

Independently verify the archive and all four uncompressed rootfs layer
digests. This requires Python source and the archived files, **not** Docker:

    python scripts/local_ai_docker.py verify-image-transfer \
      --directory "$HOME/private-offline-ai/transfer-001"

The response contains receipt_file_sha256. Compare this fingerprint through an
independent trusted channel before importing onto another machine. Treat a
hash delivered solely inside the archive as self-referential, not an
authenticity proof. A signed provenance chain would be stronger and remains
outside the current release authorization.

## Destination: read-only admission

On the disconnected destination, place the verified private archive under a
private 0700 parent. Provide the independently approved 64-hex SHA-256:

    python scripts/local_ai_docker.py --mode cpu plan-image-import \
      --directory /home/operator/private-offline-ai/transfer-001 \
      --expected-receipt-sha256 YOUR_INDEPENDENT_RECEIPT_SHA256

A passing plan checks the actual Docker daemon OS/architecture and the exact
saved image platform and size/contents. It makes no image-store changes and
does not require application setup or a model. It does **not** certify CPU
memory capacity, a CUDA/ROCm stack, WSL2, secure boot, GPU passthrough,
backend readiness, DB consistency or a protected end-to-end chat turn.

On an explicitly approved destination only:

    python scripts/local_ai_docker.py --mode cpu import-images \
      --directory /home/operator/private-offline-ai/transfer-001 \
      --expected-receipt-sha256 YOUR_INDEPENDENT_RECEIPT_SHA256 \
      --allow-image-store-mutation

Import uses only the local tar, with no image pull and no tag creation. It
loads each unique image by immutable Docker ID. If a given ID is present it is
reused, without import. If the operation fails partway, previously imported
untagged images remain; the tool intentionally never prunes an image or
attempts an unsafe automatic rollback. A subsequent invocation is
idempotent against already present IDs. No containers are started.

**Important:** the stock canonical Compose deployment may refer to named
images and a Mongo registry digest, neither of which is created by an
untagged import. This is intentionally an **image-store staging action**, not
an offline-app-launch authorization. A separately reviewed digest-bound
image reference selection and no-pull Compose admission are still required
to make staged images selectable without retagging or implicit registry
resolution. Do not replace Compose pins manually and infer protected-chat
availability.

## Modern Docker/containerd archive compatibility

Newer Docker Engine installations may save the image configuration as a
content-addressed file under `blobs/sha256/` instead of a `.json` filename.
The single-image manifest may also contain `LayerSources` descriptors and
an OCI index. The sanitizer handles that format without retaining registry
URLs, annotations or OCI index names. It preserves only the pinned image
configuration, declared layer blobs and a tagless Docker-save manifest.
Legacy Docker saves with `layer.tar` and adjacent `json`/`VERSION` remain
supported.

For OCI blobs, verification independently checks the compressed blob name's
SHA-256 **and**, when the layer is gzip-compressed, streams and hashes the
uncompressed content against the image config's ordered rootfs diffID. The
allowed layer encodings are uncompressed tar and gzip-compressed tar with
explicit per-layer expansion ceilings; unsupported encodings fail closed.
LayerSource descriptors are reduced to a bounded media type, digest and byte
size; remote URLs and arbitrary annotations cannot survive export.

## Physical synthetic Docker qualification

The isolated CI physical test creates only a fresh random disposable image by
importing a local one-file tar; it neither downloads a base image nor
starts a container. It exports that test image using its immutable ID,
neutralizes tags, validates its uncompressed layer digests, removes the
original randomized source reference, loads the neutral archive, and proves
the image ID matches and the source tag has **not** reappeared. Only that
randomized CI-created image may be removed during cleanup.

This establishes real daemon tag-neutral transfer on the CI platform; it does
not verify all four production images, GGUF weights or GPU runtime.
Source-only Python tests use synthetic tar/config data and intentionally do
not claim real Docker evidence.

## Required acceptance gates before a standalone release

1. All complete mandatory exact-head CI, source identity, security, native,
   device and release checks; no ancestor or skipped test substituted.
2. Real export of all four canonical images and independent layer verification.
3. Verified destination import with no tag collision, followed by separately
   reviewed pin-based offline Compose reference selection without pulling.
4. Real licensed GGUF/offline llama.cpp execution on the selected CPU/GPU mode.
5. Authoritative bounded independent reviewer, active GGUF tokenizer
   attestation and supported protected Jeeves bootstrap.
6. Majority-durable Mongo primary with shared epoch/writer fencing, actor
   migration, external writer exclusion and bounded replay.
7. Actual coherent database consistency/recovery rehearsal across stores
   and model/image custody; synthetic volume copies alone are insufficient.
8. Physical Windows 11/WSL2, Linux CPU/GPU, network isolation, resource
   pressure and cold restart qualification.
9. Independent signed/reproducible release provenance and user-install proof.

Until these pass: keep both the image transport and the application stack
review-only, and never represent a passed image-import test as a working,
protected standalone local AI chat.
