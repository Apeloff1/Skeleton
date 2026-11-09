# Branch snapshots are archival evidence

The directories below this path are immutable historical/reference snapshots of branches that were imported during repository consolidation. They are **not supported build, deploy, or dependency-management surfaces**.

Security rules:

- Do not install dependencies directly from a snapshot.
- Historical dependency manifests and lockfiles must use non-installable `*.snapshot` naming rather than canonical dependency-manager filenames.
- Examples include `requirements.snapshot`, `package.snapshot.json`, `yarn.snapshot.lock`, `pyproject.snapshot.toml`, and `setup.snapshot.cfg`.
- Promote code into a canonical maintained package before executing or shipping it.
- A promoted component must receive a fresh maintained dependency manifest, current vulnerability audit, tests, and the normal merge-readiness/security gates.
- Never restore canonical package-manager filenames below this directory. `scripts/check_archived_dependency_surface.py` and the Dependency Surface Guard reject them.

This keeps historical provenance intact without multiplying live dependency alerts or making stale dependency graphs accidentally executable. Git history retains the original canonical filenames and exact imported bytes; the working tree exposes only clearly quarantined evidence names.
