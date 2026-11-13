# Offline multi-game export verification

This operation extends the canonical game-builder source-bound verifier to
a complete offline cohort. It does not execute native Godot, run a model,
contact a provider, certify rights, or authorize publication.

An operator independently pins the exact SHA-256 of canonical `batch.json`:

```json
{"packages":[{"package_dir":"game-001","project_id":"original-batch-001","release_sha256":"<64 lowercase hex>"}],"schema":"skeleton.game_builder.offline_export_batch.v1"}
```

Serialize with sorted object keys, ASCII JSON, compact separators and one
trailing newline. Entries are ordered by `package_dir`. Each package is a
separate, already exported browser/Godot source directory. The batch root
contains **only** `batch.json` and the listed package directories.

```sh
python -m skeleton.ai.game_builder.original_game_studio_cli verify-batch \
  --root /trusted/offline/cohort \
  --expected-index-sha256 <independently-obtained-pin> \
  --trusted-local-operator
```

The root and each package are traversed using POSIX directory descriptors
and `O_NOFOLLOW`; each package is verified by the existing canonical
source manifest, world reconstruction and winning-action replay verifier.
All paths, names, file counts and aggregate bytes are bounded. Missing,
extra, malformed, symlinked, mutated, or unpinned entries reject the batch.
The deterministic receipt binds the exact index, project IDs, package source
digests, replay digests, and bounded aggregate evidence. A batch cannot be
accepted on a partial success.

No external credentials, network, binaries or scripts are loaded. The
operation is read-only and fail-closed on unsupported platforms. Native
Godot execution, consumer hardware qualification, legal originality and
release certification remain separate mandatory gates.

## Trusted batch preparation

A trusted local operator can author the canonical index only after the
existing game verifier has replay-proved every listed source package:

```sh
python -m skeleton.ai.game_builder.original_game_studio_cli prepare-batch \
  --root /trusted/offline/cohort \
  --package original-batch-001:game-001:<release-pin> \
  --trusted-local-operator
```

Repeat `--package` for every independently pinned original game. The
preparation operation rejects unlisted files, symlinked packages, incorrect
project identities, invalid replay, duplicate IDs, writable/unowned roots,
and an existing `batch.json`. It publishes the index using a private
same-directory temporary file, fsync and atomic no-overwrite hardlink.
No package is rewritten. A crash before publication leaves an invalid
temporary artifact requiring operator cleanup; no trusted pin is emitted.
The resulting SHA-256 is **not** a trust anchor until conveyed separately
to the verifying operator. This is source verification, not rights or native
device certification.

## Source-bound release delta

A read-only comparison independently verifies and replay-proves BOTH cohorts
before classifying added, removed, source-changed, relocated and unchanged
projects. Source changes are based on pinned release SHA-256, not project
names or timestamps. A relocation preserves the exact source digest.

```sh
python -m skeleton.ai.game_builder.original_game_studio_cli diff-batch \
  --left-root /trusted/old --left-index-sha256 <old-pin> \
  --right-root /trusted/new --right-index-sha256 <new-pin> \
  --trusted-local-operator
```

The receipt binds both independently pinned cohort receipts and every
project-level change. It is an inspection result only: it does not install,
migrate, deploy, execute native binaries, grant rights or certify release.

## Durable local verification receipts

The `verify-export`, `verify-batch` and `diff-batch` CLI commands accept
`--receipt-output /private/verified-receipt.json`. This is an optional
POSIX-only, owner-controlled, atomic no-clobber JSON publication of the
actual canonical replay result. Output must be outside every verified source
root. Symlinked parent directories, group/world-writable parents, existing
filenames and failed verification are rejected without overwriting evidence.
The receipt is **not** a signature, publisher attestation, rights clearance,
native Godot execution or device qualification. Transfer the independent
source/index SHA-256 pins separately from the untrusted package.

## Inspect an archived receipt

Run `inspect-receipt --receipt /private/verified-receipt.json
--expected-sha256 <independently-held-sha256> --trusted-local-operator`
through the canonical original-game studio CLI. This performs a read-only
bounded nofollow check of canonical JSON, independent file SHA-256, supported
receipt schema and embedded digest where present. It **does not** replay
gameplay again, validate the current source tree, execute Godot or qualify
consumer hardware. Re-run `verify-export` or `verify-batch` against the
original independently pinned sources for fresh gameplay acceptance.
