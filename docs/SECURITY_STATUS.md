# Security control status

This document is the repository-level control map for Skeleton. It records where each major security control is implemented, what regression evidence protects it, whether it participates in canonical Merge Readiness, and which guarantees still depend on repository administration or external infrastructure.

Status here is descriptive, not a substitute for GitHub issue state. Issue #540 remains the active hardening backlog and issue #127 remains the merge-enforcement backlog.

## Status vocabulary

- **Canonical** — source-controlled enforcement runs inside `.github/workflows/merge-readiness.yml` or a script/test directly invoked by its required jobs.
- **Supplemental** — source-controlled enforcement exists in another workflow or test path but is not itself one of the four aggregate Merge Readiness jobs.
- **Admin-only** — the repository can document or detect the requirement, but GitHub repository/organization settings must enforce it.
- **Pending** — tracked hardening work remains before the control can be called complete.

## CI/CD and repository trust controls

| Control | Enforcement | Regression / evidence | Status | Remaining risk |
| --- | --- | --- | --- | --- |
| Stable aggregate merge summary | `.github/workflows/merge-readiness.yml`; `scripts/check_merge_readiness_contract.py` | quarantine/unit/integration/quality jobs feed the single `Merge Readiness` summary | Canonical | `main` is currently unprotected, so the repository cannot force the summary to be required without admin settings. |
| Third-party action immutability | `backend/scripts/check_workflow_security.py` | `backend/tests/test_workflow_security_gate.py` covers tag/unversioned action rejection and SHA-pinned acceptance | Canonical | Repository administrators can still bypass source-controlled CI while `main` is unprotected. |
| Checkout credential persistence | `backend/scripts/check_workflow_security.py` | `backend/tests/test_workflow_security_gate.py`; `backend/tests/test_workflow_security_checkout_credentials.py` covers missing/true/false values plus sibling-`env`, nested-mapping, block, and flow-style bypasses | Canonical | Same branch-protection/admin bypass risk. |
| Untrusted workflow event/input shell boundary | `backend/scripts/check_workflow_input_security.py`, composed by `check_workflow_security.py` | `backend/tests/test_workflow_input_security_gate.py`; `backend/tests/test_workflow_event_shell_security.py` | Canonical | New expression forms require continuing regression coverage. |
| `pull_request_target` prohibition | `backend/scripts/check_workflow_security.py` | workflow security regressions reject the trigger | Canonical | None known in source-controlled policy; admin bypass remains external. |
| Job/service image immutability | `backend/scripts/check_workflow_container_security.py`, composed by `check_workflow_security.py` | `backend/tests/test_workflow_security_gate.py` covers mutable job/service image rejection | Canonical | Digest refresh provenance and base-image lifecycle remain tracked separately. |
| Privileged/host-sensitive CI container options | `backend/scripts/check_workflow_container_security.py` | regressions cover privileged mode, host networking, capability elevation, and Docker socket mounts | Canonical | New Docker option forms must remain fail-closed or receive explicit policy coverage. |
| Least-privilege workflow permissions | `backend/scripts/check_workflow_security.py` | workflow-security regressions cover missing permissions, `write-all`, workflow-wide write elevation, and bounded job-local elevation | Canonical | A repository-wide semantic audit of every justified job-local write grant remains tracked in #540. |
| Flaky-test quarantine | `.github/ci/flaky-quarantine.json`; `scripts/check_flaky_quarantine.py` | Merge Readiness `Quarantine Policy` job | Canonical | Quarantine expiry/ownership must remain maintained. |

## Source and runtime security controls

| Control | Enforcement | Regression / evidence | Status | Remaining risk |
| --- | --- | --- | --- | --- |
| Backend high-confidence SAST | `backend/scripts/check_sast_security.py` | `backend/tests/test_sast_security_gate.py` | Canonical | #540 still tracks verification of full canonical Python and frontend coverage. |
| Core/tooling Python SAST | `scripts/check_repository_python_sast.py` | `backend/tests/test_repository_python_sast_scope.py` | Canonical | Dynamic/runtime-only behaviors still require adversarial tests. |
| Process invocation safety | `backend/scripts/check_process_safety.py`; `scripts/check_repository_process_safety.py` | process-safety regression family under `backend/tests/` | Canonical | Continue coverage for aliases, wrappers, dynamic imports, and generated command paths. |
| Unsafe deserialization | `backend/scripts/check_deserialization_safety.py` | `backend/tests/test_deserialization_safety_gate.py` | Canonical | Broader archive/parser abuse remains tracked in #540. |
| Tar archive extraction safety | `backend/scripts/check_archive_extraction_safety.py` | `backend/tests/test_archive_extraction_safety.py`; Backend Quality and Merge Readiness invoke the gate | Canonical | The scanner enforces the Python `data` filter for backend tar extraction; other archive formats and decompression-bomb/resource limits remain tracked in #540. |
| JavaScript child-process alias safety | `backend/scripts/check_js_process_alias_safety.py` | `backend/tests/test_js_process_alias_safety.py` | Canonical | Frontend/browser-specific sink coverage still needs periodic review. |
| API payload/rate-limit/error-redaction contracts | canonical runtime tests in `tests/` | `tests/test_api_gateway_payload_reliability.py`, `tests/test_api_gateway_rate_limit_reliability.py`, `tests/test_api_gateway_error_redaction.py` | Canonical | Header limits, CORS/auth boundaries, content-type validation, and SSRF-specific coverage remain tracked in #540. |
| Outbound callback/catalog destination boundary | `skeleton/security/outbound_url.py`; webhook subscription guards; fixed-host GameForge free-API catalog with encoded parameters and bounded streamed responses | `tests/test_webhook_destination_security.py`; `backend/tests/test_free_api_network_security.py`; both are invoked by `scripts/quality-gates.sh` | Canonical | The shared URL guard covers deterministic scheme/host/literal-address policy. A real network sender must additionally validate resolved addresses at connect time to close DNS-rebinding TOCTOU risk. |
| Tool/sandbox capability boundary | provider/runtime and architecture boundary gates plus consolidated sandbox contracts | canonical architecture/provider tests and closed capability-sandbox work under parent #80 | Canonical / implemented | #540 still tracks adversarial proof that untrusted model/tool input cannot widen grants. |
| Adversarial release boundary | `skeleton/cortex/adversarial.py`; `skeleton/cortex/tri_adversarial.py` | `tests/test_adversarial_engine.py`, `tests/test_tri_adversarial_engine.py`, candidate-isolation and mutation/repair-boundary regressions | Canonical | Lane candidates and metadata are deep-isolated and judge mutation is fail-closed outside the explicit bounded repair path; new judge interfaces must preserve this invariant. |
| Application-container privilege boundary | root/backend/frontend production Dockerfiles; `docker-compose.yml` | `skeleton/testing/test_deployment_security_defaults.py` verifies non-secret deployment defaults, immutable stateful refs, `no-new-privileges`, capability drops, read-only application roots, bounded `/tmp` tmpfs, and canonical liveness probes | Implemented | Third-party database/vector images and their required writable state still require separate capability/minimization review. |

## Secrets, malware, and telemetry controls

| Control | Enforcement | Regression / evidence | Status | Remaining risk |
| --- | --- | --- | --- | --- |
| Full-history credential scanning | `.github/workflows/merge-readiness.yml` Gitleaks step plus `.gitleaks.toml` | canonical `quality_security` job | Canonical | A green current-main run is still required as execution evidence; branch protection is still admin-only. |
| Repository secret hygiene | `backend/scripts/check_secret_hygiene.py` | `backend/tests/test_secret_hygiene_gate.py` | Canonical | #540 still tracks realistic fixture/example/high-entropy false-negative audit. |
| Credential rotation/revocation procedure | `docs/SECURITY_CI_POLICY.md` | `backend/tests/test_security_policy_docs.py` | Implemented | Provider-side revocation and audit-log review necessarily happen outside source control. |
| Malware / IOC policy | `backend/scripts/check_malware_iocs.py`; `.github/workflows/malware-gate.yml` | `backend/tests/test_malware_ioc_gate.py` | Canonical + supplemental | Signatures/IOCs need maintenance as threats evolve. |
| Sensitive telemetry redaction | shared observability/redaction contracts | `tests/test_orchestration_error_redaction.py`, `tests/test_api_gateway_error_redaction.py`, observability tests | Canonical | Continue auditing workflow/runtime diagnostics for raw headers, URLs, exception payloads, and environment dumps. |

## Dependency, artifact, and release controls

| Control | Enforcement | Regression / evidence | Status | Remaining risk |
| --- | --- | --- | --- | --- |
| Dependency review / vulnerability checks | `.github/workflows/dependency-review.yml`; `.github/workflows/dependency-security.yml`; `.github/workflows/dependency-surface-guard.yml` | workflow execution plus dependency-surface policy | Supplemental / partially canonical through quality policy | #540 still tracks fail-closed verification for production Python/frontend dependency findings. |
| Artifact policy | `.github/workflows/artifact-policy.yml` | source-controlled artifact/LFS policy | Supplemental | Release retention and external storage guarantees depend on platform configuration. |
| Deployment trust | `.github/workflows/deployment-trust.yml` | deployment trust policy workflow | Supplemental | Environment protection and deploy permissions are partly repository/organization-admin settings. |
| Release provenance / attestations | provenance/release policy workflows in `.github/workflows/` | source-controlled release-evidence checks | Supplemental / pending completion | #540 still tracks refusal of release when required provenance/attestation evidence is absent. |
| Container vulnerability scanning | dependency/release security workflows | workflow evidence | Pending verification | #540 still requires proof that every deployable image is scanned for HIGH/CRITICAL findings. |
| Base/deployment image immutability | digest-pinned root/backend/frontend Dockerfiles plus digest-pinned Mongo/Chroma compose refs; CI service-image policy | `skeleton/testing/test_deployment_security_defaults.py`; workflow container scanner for CI service images | Implemented / refresh pending | Controlled digest-refresh automation and refresh provenance remain open. |

## Operational readiness

| Control | Source | Status | Remaining risk |
| --- | --- | --- | --- |
| Security ownership and response path | `docs/SECURITY_CI_POLICY.md` | Implemented | Requires maintainers to follow the documented process. |
| Cross-plane threat model | `docs/SECURITY_CI_POLICY.md` | Implemented | Must be updated when new trust boundaries are introduced. |
| Incident response and evidence preservation | `docs/SECURITY_CI_POLICY.md` | Implemented | Provider/runtime evidence retention is external to the repository. |
| Emergency merge override procedure | `docs/SECURITY_CI_POLICY.md` | Implemented | Actual bypass authority and branch-rule restoration are admin operations. |
| Security exceptions | `docs/SECURITY_CI_POLICY.md` | Implemented policy | Enforcement of every future exception still requires review discipline and regression coverage. |

## External and admin-only blockers

The following guarantees cannot be completed by repository source changes alone:

1. **Protect `main`.** Current branch metadata reports `protected: false`.
2. **Require `CI/CD / Merge Readiness`.** Required status-check enforcement is currently off and no required contexts/checks are configured.
3. **Prevent ordinary direct bypass.** Review requirements, bypass actors, rulesets, and emergency administrator authority are GitHub repository/organization settings.
4. **Protect environments and deployment credentials.** Environment reviewers, secret access, provider IAM, token lifetime, revocation, and audit retention live outside the source tree.
5. **Guarantee registry/artifact immutability.** External package/container registries and artifact stores must enforce their own retention and immutability policies.

These items must not be marked complete merely because documentation or detection exists in the repository.

## Current priority gaps

Issue #540 remains open for the following high-value work:

- repository-admin enforcement of the stable merge gate;
- semantic least-privilege audit of workflow/job token grants;
- complete network/SSRF and API boundary audit;
- fail-closed scanner self-failure regressions across the security suite;
- realistic secret-fixture/high-entropy false-negative audit;
- dependency/container vulnerability and controlled digest-refresh verification;
- runtime-secret hardening plus writable-state minimization for third-party stateful services;
- release provenance/attestation refusal behavior;
- adversarial malformed-input, traversal, archive-bomb/zip-slip, SSRF, command-injection, unsafe-serialization, and leakage tests.

## Closure rule

A source-controlled control is complete only when its implementation and regression evidence are on `main`. An enforcement control is complete only when the required workflow has successful execution evidence. An admin-only control is complete only when the corresponding repository/provider setting is actually enabled and verified.
