# Repository Intelligence Indexes

The bot uses small deterministic indexes so model context stays targeted and reproducible.

| Index | Purpose |
|---|---|
| File | path, digest, size, line count, type |
| Documentation | README/docs headings and relationships |
| Symbol | functions, classes, methods and definitions |
| Reference | imports, calls and file references |
| Dependency | manifests, lockfiles, package/version relationships |
| Workflow | triggers, permissions, actions, jobs and gates |
| Test | tests mapped to modules and security properties |
| Finding | issue/alert/run → affected files/symbols |
| PR | changed files, checks, review state and lineage |
| Failure | normalized CI failure fingerprints |
| Security | scanners, severities, evidence and remediation state |
| Container | Dockerfiles, bases, packages, users and runtime controls |
| Secret boundary | secret-like paths, exclusions and scanner evidence |

## Index invariants

- Indexes are deterministic for the same commit.
- Every record carries the source commit SHA.
- Deleted or changed files invalidate dependent records.
- No index grants execution capability.
- Untrusted text is stored as data and cannot alter policy.
- Secrets are represented by redacted metadata, never plaintext.
- Index rebuilds are idempotent.
- Partial indexing records an explicit incomplete state.

## Retrieval priority

1. exact finding evidence
2. affected symbol/file
3. focused regression tests
4. relevant workflow and CI evidence
5. dependency/container context
6. nearby documentation
7. broader repository context only when required

The model should receive the smallest evidence set that can support the current decision.
