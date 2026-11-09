# Releasing

1. **Version source of truth:** `[project].version` in the repo-root `pyproject.toml` (semver, no `v`). `backend/pyproject.toml`, `frontend/package.json` and `frontend/app.json` must match it. (A separate `VERSION` file isn't used, because root-level extensionless files are rejected by Changed-files hygiene.) `python scripts/check_version_drift.py` fails on drift, and `tests/test_release_versioning.py` runs it in CI.
2. **Bump:** edit the root `pyproject.toml` version and the three other manifests in one PR, then check with `python scripts/check_version_drift.py`.
3. **Changelog:** `python scripts/generate_changelog.py --version X.Y.Z` prints a Markdown section grouped by Conventional Commit type since the previous `v*` tag. Paste it into `CHANGELOG.md` in the bump PR.
4. **Tag:** after the bump PR merges, push tag `vX.Y.Z` on that commit. `.github/workflows/release-images.yml` then:
   - verifies the tag matches the canonical version;
   - writes the changelog section to the run summary;
   - builds and pushes `ghcr.io/apeloff1/skeleton-backend:X.Y.Z` and `ghcr.io/apeloff1/skeleton-frontend:X.Y.Z` (plus `latest`), authenticating with the built-in `GITHUB_TOKEN` (`packages: write`). No other secrets are involved.
5. **Runtime version:** release images are built with `APP_VERSION=X.Y.Z`, and the backend exposes it as `codedock_build_info{version="X.Y.Z"}` on `/api/metrics`.

`workflow_dispatch` on Release Images is a dry run: it builds both images locally, checks the version label, `APP_VERSION` and non-root user, and pushes nothing.
