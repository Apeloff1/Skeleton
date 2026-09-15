# Artifact Placement & Provenance Policy

Issue: #125.

This policy keeps Skeleton reconstructible from source without turning Git into a binary warehouse. It applies incrementally: the repository gate checks new or changed files, so legacy tracked blobs remain explicit migration debt while new bloat is blocked immediately.

## Placement decision

Use the first matching lane.

| Asset | Placement | Rule |
|---|---|---|
| source, config, docs, compact fixtures | normal Git | keep individual blobs <= 10 MiB |
| model weights, tensor/array datasets, large binary runtime assets that must version with source | Git LFS | require provenance sidecar and SHA-256 |
| APK/AAB/IPA, wheels, archives, generated packages, build outputs | CI/release artifact storage | never commit to source Git, even via LFS |
| large datasets/models that do not need source-level versioning | external object/model storage | pin immutable version/checksum in source metadata |
| caches, runtime vaults, generated scratch state | nowhere in Git | regenerate locally/CI; keep ignored |

The policy gate is `scripts/check_artifact_policy.py` and is enforced both in pre-commit and GitHub Actions.

## Normal Git

Normal Git is for reviewable, diffable repository inputs. New or changed regular Git blobs must be **10 MiB or smaller**.

Small binary test fixtures are allowed when all of these are true:

- path contains `tests/fixtures/` or `testing/fixtures/`;
- file is 1 MiB or smaller; and
- the fixture is required for deterministic tests.

Do not split a large generated artifact into many sub-10-MiB files to evade the limit. That is still artifact-storage misuse.

## Git LFS

The following binary/model/data formats require Git LFS unless they are bounded small test fixtures:

- `.pt`, `.pth`, `.ckpt`, `.onnx`, `.safetensors`
- `.h5`, `.hdf5`, `.npy`, `.npz`, `.parquet`, `.arrow`, `.bin`

A changed LFS asset must have a sibling provenance file named `<asset-filename>.artifact.json` containing an exact lowercase SHA-256, a source locator (or `generated:<command>`), and an explicit license.

The gate verifies the sidecar SHA-256 against either the real local file or the OID embedded in a Git LFS pointer. Do not hand-edit LFS pointers.

## Release / CI artifacts

Generated packages and archives belong outside source Git. The gate rejects `.apk`, `.aab`, `.ipa`, `.whl`, `.zip`, `.7z`, `.tar`, and `.tgz` when newly added or changed.

Build workflows should publish these as CI/release artifacts with source commit, dependency/toolchain provenance, and checksums. A release artifact should be reproducible from a clean checkout or have a documented reason why it cannot be.

## External large assets

Use external object/model storage when the asset is large, frequently replaced, or not necessary to review source changes. Source code must pin enough metadata to reproduce retrieval: immutable version/object identifier, SHA-256, source/provider locator, license/redistribution status, and deterministic download/build instructions. Do not depend on an unversioned `latest` URL for required development or release inputs.

## Generated/runtime state

Generated caches, runtime vaults, package-manager stores, test caches, and build outputs must not become tracked source. `.gitignore` remains the first line of defense; the artifact policy is the fail-closed backstop for force-added files and ignore drift.

## Local usage

Pre-commit checks staged files automatically. Manual equivalents:

```bash
python scripts/check_artifact_policy.py --staged
python scripts/check_artifact_policy.py --base origin/main
python scripts/check_artifact_policy.py --all
```

`--all` may report grandfathered legacy debt. Do not weaken the policy to make a legacy audit green; migrate each finding deliberately.

## Legacy migration rule

Existing large/binary tracked files are migration debt until moved to the correct lane. When migrating an existing asset: identify every consumer, record checksum/source/license provenance, move it to LFS or external/release storage, update reproducible fetch/build instructions, and validate a fresh checkout/build without hidden local files. History rewriting is optional cleanup and must not substitute for making the current tree reproducible.

## Pull-request expectations

A PR introducing a new large asset must explain why the chosen storage lane is correct. For LFS/external assets, reviewers should verify provenance and license before merge. For generated release outputs, the PR should change the build recipe—not commit the output itself.
