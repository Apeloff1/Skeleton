# Security Status and Control Map

Snapshot basis: live GitHub branch metadata at `main` commit `6cdd2bb5e7b5f186671790b1ea63cf1dded8c020` on 2026-10-28 (inspection only, not production certification).

This map separates repository-controlled security controls from GitHub/deployment-admin controls. It does not claim that queued CI is green; current workflow results remain the execution authority.

## Verified P0/P1 posture and operator closure

- **P0, missing GitHub enforcement:** `GET /branches/main` reported `protected=false`, required status enforcement `off`, and no required contexts; `GET /rulesets` returned no rulesets. The policy file does not install protection. An owner/admin must apply `scripts/configure_main_protection.sh --apply` with a GitHub CLI credential that has Administration permission and then run `--verify`; this connection cannot perform admin writes.
- **P0, exact-head security failure:** PR #4348's Workflow Input Security run `40632224617` failed the concurrency audit because owner historical cleanup had a job-only concurrency lock. The repaired workflow has a per-run outer key and retains the owner-gated shared job lock; successful rerun is still mandatory.
- **P0, merged without certification:** PR #4350 and PR #4349 merged while their exact-head checks were queued or pending. Automatic merging now explicitly denies operation when branch metadata says protection is disabled or unreadable; manually authorized pushes still require administrative protection.
- **P1, Actions capacity:** 166 runs were queued in the observed repository-wide snapshot. Queue relief has been assigned to the separately demonstrated ARM runner pool; neither a queued nor a cancelled workflow is a pass.
- **P1, historical cleanup:** Run `40631914620` verified 11 preexisting absences, no newly completed deletions and 19 provider-refused HTTP 403 targets. Retain these as unresolved provider restrictions; never claim they were deleted.
- **P1, production qualification:** merged context archive #4349 documents independently provisioned KMS/witness, writer migration, native attestation, external custody and crash/restore proof as outstanding. `machine/ai_capabilities.json` still marks all 10 enabled product capabilities partial or transport/source partial.
- **Exact-head release path:** after administrative protection, require current-head `Merge Readiness`, `Workflow Input Security`, `Secret scanning`, `Malware Gate`, `Repository Hygiene Gate`, `Backend Quality` and `App Foundation E2E` conclusions to be successful; track deployment-specific context-custody evidence separately. Do not count missing, skipped or cancelled gates as successes.

Earlier security rows below describe implemented controls **in repository source**, not verified live enforcement or passing current CI.

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

1. **Branch protection / required checks (P0, still outstanding).** The live 2026-10-28 snapshot confirms `main` is unprotected and lacks required checks. The owner/admin must apply and verify the stable `Merge Readiness` branch protection. The auto-merge runtime guard prevents automatic merging without protection but cannot stop direct pushes while the server-side rule is absent.
2. **Emergency bypass governance.** Define who may bypass a broken gate, what evidence is required, and how the bypass is reviewed afterward.
3. **Runtime secret storage.** Verify deployed environments inject credentials from an approved secret/configuration plane rather than baking them into images or artifacts.
4. **Network egress.** Repository code cannot alone guarantee production firewalling, metadata-service blocking, DNS policy, or egress allowlists.
5. **Runtime container policy.** Verify production workloads run non-root where supported, drop unnecessary capabilities, avoid privileged mode, and use read-only filesystems/mount allowlists where compatible.
6. **Security notifications and ownership.** GitHub alert routing, private vulnerability-reporting availability, and maintainer notification targets are repository/account settings and should be reviewed periodically.

## Fail-closed expectations

A security control is unhealthy if a scanner cannot initialize or finish, required evidence is missing, a required immutable reference becomes mutable, workflow input cannot be audited safely, provenance/test evidence disappears, or a required security job fails. Those conditions should block the protected path rather than degrade silently.

## Maintenance rule

Update this map whenever a security workflow is added, renamed, replaced, or removed; when ownership moves between repository and infrastructure; or after an incident invalidates a documented assumption. Keep the snapshot commit explicit so stale status is visible.
