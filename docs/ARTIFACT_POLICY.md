# Repository Artifact Policy

Skeleton separates source code from large runtime artifacts so repository history remains cloneable, reviewable, and reproducible.

## Ordinary Git

Commit source, configuration templates, schemas, small deterministic fixtures, documentation, lockfiles, migration files, and scripts required to reproduce builds.

Do not commit generated caches, virtual environments, dependency installation trees, compiled Python bytecode, editor/OS metadata, or temporary build output. `check_artifact_policy.py` enforces the highest-confidence exclusions against tracked paths.

## Git LFS

Model and checkpoint formats are declared as Git LFS content in `.gitattributes`:

- `.safetensors`
- `.gguf`
- `.ckpt`
- `.pt`
- `.pth`
- `.onnx`
- `.tflite`

Adding a new heavyweight model format requires an LFS rule before the artifact is committed. Existing ordinary-Git binary history is not automatically rewritten by changing `.gitattributes`; migration of existing blobs must be planned separately so history is not destructively rewritten without review.

## CI/release artifacts

Generated SBOMs, build provenance, checksums, test reports, coverage output, packaged applications, and other reproducible build products belong in CI/release artifact storage rather than source history unless there is a specific reviewable reason to retain a small fixture.

Security CI currently emits a `security-build-evidence` artifact containing the CycloneDX SBOM, provenance manifest, and SHA-256 checksums.

## External/object storage

Large datasets, model weights, generated media corpora, backups, and multi-gigabyte binary assets that do not benefit from Git review should use approved object/artifact storage. Keep a small source-controlled manifest containing origin/provenance, expected checksum, license/usage constraints, retrieval instructions, and the version needed by the application.

## Reproducibility requirement

A fresh checkout must not depend on undocumented files from a developer workstation. Any required excluded artifact must be discoverable through documented build/download steps and verifiable by checksum or signed provenance.

## Secret boundary

Never store credentials in Git, Git LFS, release artifacts, dataset manifests, checksums, or provenance files. Artifact metadata may contain secret *names* or provider identifiers when needed for operations, but never secret values.
