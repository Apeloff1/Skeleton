# Typed Jeeves read-only world workflow

The world batch plane turns a fixed operator prompt and up to eight explicit
typed requests into a deterministic, catalog-leased plan. It executes only
source-reviewed, **read-only** Jeeves world tools. Tool names must be present
in the static router catalog **and** the reviewed explicit-no-write
adapter allowlist. Legacy tools with missing write evidence are excluded.
Unknown schemas, dynamic imports, embedded
authorization, authoring tools, recursive batch calls, and unverified write
evidence fail closed. Every nested tool rechecks its own canonical source,
quest session and rights/continuity prerequisites.

`scripts/studio_world_batch_cli.py` accepts `--expected-catalog`,
`--prompt --requests '<JSON array>'`, `--plan '<receipt>'`,
`--import-plan <private export> --baseline-plan '<receipt>'`, or
`--restore <directory>`. The operator may request `--html-sha256`,
`--editor-directory` and `--publish`. The offline CSP-hashed editor exports
typed JSON; it cannot execute tools. Import verifies the catalog and baseline
plan digests. Publication is exclusive, descriptor-anchored and fsynced.
Restore re-executes the read-only plan against current canonical sources and
compares the complete receipt, refusing drift.

The static Jeeves router exposes `studio_original_world_batch`.
The batch tool does not grant authoring permission, write to files, or
certify native/device/release readiness. Playable manifests are produced
only when an underlying source-verified tool explicitly returns one; this
batch cannot invent them.

Focused regression contract:
`pytest -q tests/test_studio_world_batch.py`.
