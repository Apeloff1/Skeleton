# Artifact Placement & Provenance Policy

Issue: #125.

This policy keeps Skeleton reconstructible from source without turning Git into a
binary warehouse. It applies incrementally: the repository gate checks new or
changed files, so legacy tracked blobs remain explicit migration debt while new
bloat is blocked immediately.

## Placement decision

Use the first matching lane.

| Asset | Placement | Rule |
|---|---|---|
| source, config, docs, compact fixtures | normal Git | keep individual blobs <= 10 MiB |
| model weights, tensor/array datasets, large binary runtime assets that must version with source | Git LFS | require provenance sidecar and SHA-256 |
| APK/AAB/IPA, wheels, archives, generated packages, build outputs | CI/release artifact storage | never commit to source Git, even via LFS |
| large datasets/models that do not need source-level versioning | external object/model storage | pin immutable version/checksum in source metadata |
| caches, runtime vaults, generated scratch state | nowhere in Git | regenerate locally/CI; keep ignored |

The policy gate is `scripts/check_artifact_policy.py` and is enforced both in
pre-commit and GitHub Actions.

## Normal Git

Normal Git is for reviewable, diffable repository inputs. New or changed regular
Git blobs must be **10 MiB or smaller**.

Small binary test fixtures are allowed when all of these are true:

- path contains `tests/fixtures/` or `testing/fixtures/`;
- file is 1 MiB or smaller; and
- the fixture is required for deterministic tests.

Do not split a large generated artifact into many sub-10-MiB files to evade the
limit. That is still artifact-storage misuse.

## Git LFS

The following binary/model/data formats require Git LFS unless they are bounded
small test fixtures:

- `.pt`, `.pth`, `.ckpt`, `.onnx`, `.safetensors`
- `.h5`, `.hdf5`, `.npy`, `.npz`, `.parquet`, `.arrow`, `.bin`

A changed LFS asset must have a sibling provenance file named:

```text
<asset-filename>.artifact.json
```

Example for `models/router.onnx`:

```json
{
  "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "source": "https://example.invalid/releases/router-v3.onnx",
  "license": "Apache-2.0"
}
```

`source` may also use `generated:<command-or-build-id>` for reproducibly generated
assets. `license` must be explicit; use `Proprietary` only when repository
maintainers have confirmed redistribution is allowed.

The gate verifies the sidecar SHA-256 against either the real local file or the
OID embedded in a Git LFS pointer. Do not hand-edit LFS pointers.

## Release / CI artifacts

Generated packages and archives belong outside source Git. The gate rejects at
least these output formats when newly added or changed:

- `.apk`, `.aab`, `.ipa`
- `.whl`
- `.zip`, `.7z`, `.tar`, `.tgz`

Build workflows should publish these as CI/release artifacts with source commit,
dependency/toolchain provenance, and checksums. A release artifact should be
reproducible from a clean checkout or have a documented reason why it cannot be.

## External large assets

Use external object/model storage when the asset is large, frequently replaced,
or not necessary to review source changes. Source code must pin enough metadata
to reproduce retrieval:

- immutable version/object identifier;
- SHA-256 checksum;
- source/provider locator;
- license/redistribution status;
- deterministic download/build instructions.

Do not depend on an unversioned `latest` URL for required development or release
inputs.

## Generated/runtime state

Generated caches, runtime vaults, package-manager stores, test caches, and build
outputs must not become tracked source. The policy explicitly rejects known
runtime/build paths including Skeleton build/galaxy vault outputs and common
cache directories.

`.gitignore` remains the first line of defense; the artifact policy is the
fail-closed backstop for files that are force-added or whose ignore rule drifts.

## Local usage

Pre-commit checks staged files automatically. Manual equivalents:

```bash
python scripts/check_artifact_policy.py --staged
python scripts/check_artifact_policy.py --base origin/main
```

A full repository audit is available for migration work:

```bash
python scripts/check_artifact_policy.py --all
```

`--all` may report grandfathered legacy debt. Do not weaken the policy to make a
legacy audit green; migrate each finding deliberately.

## Legacy migration rule

Existing large/binary tracked files are not silently declared compliant. They
are migration debt until moved to the correct lane. In particular, the historic
tracked Godot runtime noted in `BACKLOG.md` should be migrated to LFS/artifact
storage under the F-11 cleanup rather than grandfathered as a pattern for new
binaries.

When migrating an existing asset:

1. identify every consumer and deployment path;
2. record checksum/source/license provenance;
3. move the asset to LFS or external/release storage;
4. update reproducible fetch/build instructions;
5. validate a fresh checkout/build without hidden local files;
6. only then consider history cleanup if repository size warrants it.

History rewriting is optional cleanup and must not be used as a substitute for
making the current tree reproducible.

## Pull-request expectations

A PR introducing a new large asset must explain why the chosen storage lane is
correct. For LFS/external assets, reviewers should verify provenance and license
before merge. For generated release outputs, the PR should change the build
recipe—not commit the output itself.
