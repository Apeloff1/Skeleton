# Repository Intelligence Indexes

The bot uses small deterministic indexes so model context stays targeted and reproducible. Indexes are derived data: they do not execute repository content and do not grant an LLM permissions.

| Index | Purpose | Primary key |
|---|---|---|
| File | path, digest, size, line count, type | commit + path |
| Documentation | README/docs headings and relationships | commit + path + heading |
| Symbol | functions, classes, methods and definitions | commit + path + symbol + kind |
| Reference | imports, calls and file references | commit + source + target + kind |
| Dependency | manifests, lockfiles, package/version relationships | commit + path + dependency + source |
| Workflow | triggers, permissions, actions, jobs and gates | commit + workflow path + job |
| Test | tests mapped to modules and security properties | commit + test path |
| Finding | issue/alert/run to affected files/symbols | repository + finding fingerprint |
| PR | changed files, checks, review state and lineage | repository + PR number |
| Failure | normalized CI failure fingerprints | repository + run + fingerprint |
| Security | scanners, severities, evidence and remediation state | repository + finding fingerprint |
| Container | Dockerfiles, bases, packages, users and runtime controls | commit + Dockerfile + stage |
| Secret boundary | secret-like paths, exclusions and scanner evidence | commit + path + boundary |
| API surface | routes, handlers, request limits and auth boundaries | commit + path + symbol |
| Config | security-sensitive configuration and defaults | commit + path + key |
| Ownership | CODEOWNERS and responsible-area metadata | commit + path/pattern |
| Release/Provenance | tags, artifacts, SBOM/provenance references | repository + release/artifact |
| History/Remediation | prior fixes, regressions and linked findings | repository + finding fingerprint |
| Event/State | durable automation state and lifecycle transitions | repository + work key |

## Invariants

- Indexes are deterministic for the same commit.
- Every repository-derived record carries the source commit SHA or an explicit historical reference.
- Every finding-derived record has a stable fingerprint independent of transient workflow run IDs.
- Deleted or changed files invalidate dependent records.
- No index grants execution capability or changes GitHub permissions.
- Untrusted text is stored as data and cannot alter policy.
- Secrets are represented by redacted metadata, never plaintext.
- Index rebuilds are idempotent and safe to repeat.
- Partial indexing records an explicit incomplete state rather than pretending coverage is complete.
- Cached conclusions are invalidated when a PR base, head SHA, or relevant finding evidence changes.

## Retrieval priority

1. exact finding evidence
2. affected symbol/file
3. focused regression tests
4. relevant workflow and CI evidence
5. dependency/container context
6. security and architecture documentation
7. history/remediation evidence
8. broader repository context only when required

The model should receive the smallest evidence set that can support the current decision. Retrieval results must retain provenance so every conclusion can be traced back to a commit, finding, file, test, workflow, or historical event.

## Rebuild and corruption behavior

Indexes are disposable derived state. A missing, stale, malformed, or partially corrupted index is rebuilt from authoritative GitHub/repository data. The bot must not repair the index by executing repository code or by trusting model-generated records.

When two index sources disagree, preserve both observations with provenance and mark the relationship as unresolved. Do not silently select the less restrictive security interpretation.
