# Branch snapshots are archival evidence

The directories below this path are immutable historical/reference snapshots of branches that were imported during repository consolidation. They are **not supported build, deploy, or dependency-management surfaces**.

Security rules:

- Do not install dependencies directly from a snapshot.
- Historical Python dependency lists are stored as `requirements.snapshot`, not `requirements.txt`, so dependency tooling cannot mistake them for supported manifests.
- Promote code into a canonical maintained package before executing or shipping it.
- A promoted component must receive a fresh maintained dependency manifest, current vulnerability audit, tests, and the normal merge-readiness/security gates.
- Never restore an installable `requirements.txt` below this directory. The dependency-surface guard rejects it.

This keeps historical provenance intact without multiplying live dependency alerts or making stale dependency graphs accidentally executable.
