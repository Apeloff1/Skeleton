# Security CI and Merge Policy

This document defines the minimum security evidence required before changes to Skeleton are considered merge-ready.

## Required pull-request gates

`Backend Quality` is the fast fail-closed security boundary. It must complete successfully on the exact pull-request head SHA. A green result from an older head is not valid evidence for a newer commit.

The job currently enforces:

- Ruff lint and full backend syntax compilation.
- Process invocation policy: no shell command construction or opaque subprocess invocation.
- Deserialization policy: no unsafe pickle/dill/marshal/YAML/object loading paths.
- High-confidence Python SAST policy: no `eval`/`exec`, disabled TLS verification, unsafe temporary-file creation, or JWT signature-verification bypasses.
- GitHub Actions policy: explicit permissions, immutable action SHAs, no `pull_request_target`, and no `write-all`.
- Repository secret hygiene scanning.
- Immutable dependency declaration policy.
- Known-vulnerability audit for Python production dependencies using OSV.
- Deterministic CycloneDX SBOM generation.
- Build provenance and SHA-256 evidence generation.
- Focused security regression tests for client identity, proxy trust, body limits, request IDs, rate limiting, configuration, SSRF protections, import/export escaping, and policy scanners.

The broader repository CI, lint, product convergence, execution evidence, deployment trust, and CodeQL checks remain independently authoritative for their respective surfaces.

## Head-SHA rule

A merge decision must refer to the current PR head SHA. Any code or workflow change invalidates previous green results and requires a new validation wave. PR descriptions must not present stale validation as current.

## Failure handling

Security failures are fixed in code or dependency declarations. Do not solve a failing security gate by:

- adding blanket ignores;
- changing the workflow to `continue-on-error`;
- weakening severity thresholds without a documented issue and expiry;
- replacing immutable action SHAs with moving tags;
- removing the failing regression test;
- hiding findings from logs without fixing the underlying condition.

A narrow exception, when unavoidable, must identify the advisory/rule, affected component, compensating control, owner, rationale, and expiry date in a tracked GitHub issue.

## Dependency exceptions

Production Python dependencies are exact-pinned. Frontend registry ranges are permitted only with the committed Yarn lockfile and integrity-pinned package manager. URL, git, file, wildcard, and mutable alias declarations are rejected by policy.

A known vulnerability should be remediated by upgrading, replacing, or removing the affected dependency. If no fixed version exists, document the exposure and compensating control before considering an exception.

## CI supply-chain rules

Third-party GitHub Actions must be pinned to full commit SHAs. Workflow permissions default to `contents: read`; jobs receive write permissions only when their behavior strictly requires them. Privileged workflow events that execute untrusted pull-request code are prohibited.

## Evidence retention

Backend Quality produces `security-build-evidence`, containing:

- `sbom.cdx.json` — CycloneDX dependency inventory;
- `build-provenance.json` — source/material hashes and builder identity;
- `SHA256SUMS` — independent checksums for the evidence files.

Release workflows should carry the same evidence forward with release artifacts rather than regenerating metadata from a different source tree.

## Flaky tests

A flaky security test remains a failure until its nondeterminism is understood. Quarantine requires a tracking issue, named owner, reproduction evidence, and expiry. Quarantine must never silently convert a security regression into a passing required check.

## Local validation

Before pushing security-sensitive changes, run the same repository-native policy scripts used by CI from `backend/`:

```text
python scripts/check_process_safety.py
python scripts/check_deserialization_safety.py
python scripts/check_sast_security.py
python scripts/check_workflow_security.py
python scripts/check_secret_hygiene.py
python scripts/check_dependency_policy.py
```

Then run the focused regression files listed in `.github/workflows/backend-quality.yml`.
