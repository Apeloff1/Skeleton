# Frontier asset policy

The 5–15 GB target is an **asset envelope**, not a license to inflate Git history.

## Git

Keep source, schemas, tests, small fixtures, and reproducible manifests in ordinary Git.

## Large assets

Models, checkpoints, embedding stores, datasets, generated media, and release bundles must use Git LFS, release assets, or external artifact/object storage. Every large asset needs a manifest entry containing provenance, license, checksum, size, and retrieval location.

## Never promote

- secrets or credential files
- `.env` files containing values
- dependency caches
- package-manager caches
- local database files
- temporary model downloads
- generated build directories
- duplicate historical snapshots

## Target envelope

A healthy full distribution may eventually contain roughly 5–15 GB across source, LFS-managed models, RAG datasets, world/game assets, audio/visual assets, benchmarks, and release artifacts. The working Git checkout should remain substantially smaller.
