# Branch snapshots are archival evidence

Full imported branch payloads are intentionally **not kept at repository tip**. They were historical/reference snapshots from repository consolidation, not supported build, deploy, test, or runtime surfaces. Their exact bytes remain recoverable from Git history without forcing every clone, indexer, scanner, and CI job to traverse duplicate working-tree copies.

The only files retained below snapshot directories are quarantined dependency-manifest evidence referenced by DEPENDENCY_ARCHIVE_MAP.json. Those files keep their original Git blob identity under non-installable snapshot names so provenance checks can verify them without exposing stale dependency graphs as live package-manager surfaces.

Security and hygiene rules:

- Do not restore full branch payloads under this directory; use Git history when historical code is needed.
- Do not install dependencies directly from snapshot evidence.
- Keep historical manifests under non-installable snapshot names such as requirements.snapshot, package.snapshot.json, yarn.snapshot.lock, pyproject.snapshot.toml, and setup.snapshot.cfg.
- Promote useful historical code into a canonical maintained package before executing or shipping it.
- A promoted component must receive current dependency metadata, vulnerability review, tests, and normal merge-readiness/security gates.
- scripts/check_archived_dependency_surface.py rejects installable manifests, unmapped evidence, and any bulk snapshot payload that reappears at repository tip.
