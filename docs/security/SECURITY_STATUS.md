# Security Status and Control Map

Snapshot basis: `main` at `55414bdff9404e67c025a7e2b902bc45e02c558e` on 2026-09-15.

This map separates repository-controlled security controls from GitHub/deployment-admin controls. It does not claim that queued CI is green; current workflow results remain the execution authority.

## Control map

| Security objective | Canonical repository evidence | Enforcement / regression surface | Status at snapshot |
| --- | --- | --- | --- |
| Deterministic merge gate | `.github/workflows/merge-readiness.yml`, `docs/MERGE_READINESS.md`, `docs/CI_REQUIRED_CHECKS.md` | Merge Readiness | Implemented in repo; required-check enforcement remains external |
| Workflow trust boundary | `backend/scripts/check_workflow_security.py` and focused tests | Backend Quality / canonical quality gate | Implemented, including immutable CI containers and runner-escape option rejection |
| Immutable third-party Actions | workflow-security policy | Workflow-security regression suite | Implemented policy |
| Immutable CI job/service containers | workflow-security policy and digest-pinned current services | Workflow-security regression suite | Implemented on current main |
| Secret detection and history hygiene | `.gitleaks.toml`, `docs/security/SECRET_HYGIENE.md`, secret-scanning workflow | Secret scanning | Implemented; confirmed findings still require operational revocation/rotation |
| Dependency review | `.github/workflows/dependency-review.yml`, `.github/workflows/dependency-security.yml` | Dependency Review / dependency security | Implemented |
| Malware / IOC detection | canonical malware workflow and tests | Malware Gate | Implemented |
| Artifact admission | `.github/workflows/artifact-policy.yml`, `docs/ARTIFACT_POLICY.md` | Artifact Policy | Implemented |
| Provenance validation | consolidation manifest/evidence runner and provenance workflow | Provenance Policy | Implemented for declared canonical components; broader promotion coverage remains ongoing |
| Tool capability isolation | `docs/TOOL_CAPABILITIES.md` and capability regressions | quality/integration security tests | Implemented deny-by-default contract |
| Provider failure sanitization / bounded retry | `docs/PROVIDER_RUNTIME.md`, `docs/PROVIDER_STREAM_RELIABILITY.md` and focused tests | Backend Quality / Merge Readiness | Implemented on canonical runtime |
| Durable-state recovery / idempotency | `docs/DURABLE_RUN_STATE.md`, storage chaos/reliability tests | Durable State / canonical quality checks | Implemented on canonical state path |
| Observability redaction / correlation | `docs/OBSERVABILITY.md` and observability regressions | Backend Quality / Integration Smoke | Implemented on canonical execution path |
| Incident handling | `docs/SECURITY_INCIDENT_RESPONSE.md` | Maintainer operational procedure | Documented |
| Vulnerability intake | `SECURITY.md` | Maintainer operational procedure | Added by this change |
| Threat model | `docs/security/THREAT_MODEL.md` | Maintainer review trigger | Added by this change |

## External / admin-owned residual risks

1. **Branch protection / required checks.** At the snapshot, `main` is not protected and has no required status checks configured. Repository administration should require the stable Merge Readiness check and restrict direct bypass.
2. **Emergency bypass governance.** Define who may bypass a broken gate, what evidence is required, and how the bypass is reviewed afterward.
3. **Runtime secret storage.** Verify deployed environments inject credentials from an approved secret/configuration plane rather than baking them into images or artifacts.
4. **Network egress.** Repository code cannot alone guarantee production firewalling, metadata-service blocking, DNS policy, or egress allowlists.
5. **Runtime container policy.** Verify production workloads run non-root where supported, drop unnecessary capabilities, avoid privileged mode, and use read-only filesystems/mount allowlists where compatible.
6. **Security notifications and ownership.** GitHub alert routing, private vulnerability-reporting availability, and maintainer notification targets are repository/account settings and should be reviewed periodically.

## Fail-closed expectations

A security control is unhealthy if a scanner cannot initialize or finish, required evidence is missing, a required immutable reference becomes mutable, workflow input cannot be audited safely, provenance/test evidence disappears, or a required security job fails. Those conditions should block the protected path rather than degrade silently.

## Maintenance rule

Update this map whenever a security workflow is added, renamed, replaced, or removed; when ownership moves between repository and infrastructure; or after an incident invalidates a documented assumption. Keep the snapshot commit explicit so stale status is visible.
