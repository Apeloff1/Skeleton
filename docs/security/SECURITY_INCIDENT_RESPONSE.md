# Production Security and Incident-Response Runbook

This runbook is the operational response guide for security and reliability incidents in Skeleton. It deliberately references repository controls that exist on `main`; where deployment, backup, or infrastructure commands are environment-specific, operators must use the documented procedure for that environment rather than improvising a command from this file.

## 1. Response priorities

Protect people and data first, then contain the incident, preserve evidence, restore service safely, and only then optimize for speed.

### Severity

- **SEV-1 / critical:** confirmed credential compromise with production access, active exploitation, unauthorized code or CI modification, destructive data impact, or broad production outage. Escalate immediately, freeze risky deploys, and keep an incident lead on the event until containment and recovery criteria are met.
- **SEV-2 / high:** suspected compromise, sustained abuse, proxy/client-identity failure, exploitable dependency finding, repeated 5xx/rate-limit saturation, or degraded service with a credible security boundary impact. Escalate to the service/security owner and prepare rollback if the condition is not quickly contained.
- **SEV-3 / moderate:** isolated policy-gate failure, non-production exposure, low-impact dependency alert, or recoverable service regression with no evidence of compromise. Track to closure and promote to SEV-2 if scope grows.

### Mandatory rollback triggers

Rollback to a known-good release or commit when a newly deployed change is strongly correlated with active exploitation, unauthorized access, persistent 5xx/degradation, broken client-identity enforcement, disabled security validation, or a failed security gate that affects production assumptions. Do not rollback across a data/schema incompatibility until the owning runbook confirms that the rollback is safe.

## 2. First 15 minutes

1. Assign an incident lead and record the start time in UTC.
2. Freeze non-essential production deploys and automation that could destroy evidence or widen impact.
3. Record the deployed commit SHA, release identifier, affected environment, relevant workflow-run IDs, request IDs, timestamps, and observable symptoms. Never copy a real secret into the incident record.
4. Preserve original logs and artifacts before rotating, deleting, rebuilding, or rewriting anything. Record hashes when practical.
5. Classify severity and affected boundaries: credentials, network/proxy identity, rate limiting, dependencies/supply chain, CI, unsafe execution/deserialization, data/state, or availability.
6. If a recent change is the likely trigger and rollback is safe, revert to the last verified good release while continuing evidence collection.
7. After containment, validate with repository gates before declaring recovery.

## 3. Pre-deploy and recovery validation

Run the canonical local verification suite from the repository root:

```bash
bash scripts/quality-gates.sh
```

Relevant CI controls are:

- `.github/workflows/backend-quality.yml` — lint, compile, security-policy scanners, and focused adversarial regression tests.
- `.github/workflows/secret-scanning.yml` — full-history Gitleaks scanning using `.gitleaks.toml`.
- `.github/workflows/dependency-security.yml` — Python and JavaScript dependency auditing plus CycloneDX SBOM artifacts.

A production recovery is not complete while a gate relevant to the incident remains red or unexplained.

## 4. Suspected credential or secret exposure

Treat a credential that reached Git history, an issue, build artifact, log, package, or unauthorized party as compromised even if it is later deleted from the visible source.

1. Revoke the exposed credential at its provider. If immediate revocation would create a larger outage, provision a replacement through the approved secret store, deploy it, verify service health, then revoke the exposed value.
2. Identify the credential type and affected commits, refs, artifacts, logs, packages, and environments without copying the secret value into tickets or chat.
3. Rotate dependent or paired credentials when the exposed material could be reused to derive access.
4. Remove the source from tracked code and replace it with an environment/configuration lookup or obviously synthetic placeholder.
5. If the value entered Git history, coordinate any history rewrite and force-update before collaborators resume pushing. Revocation is still mandatory after a history purge.
6. Delete or expire affected CI artifacts, container layers, release archives, caches, or package versions.
7. Review provider access logs from the earliest possible exposure through revocation and escalate unexplained use to SEV-1.
8. Run `python backend/scripts/check_secret_hygiene.py` and require the `Secret scanning` workflow to pass before closure.

Do not create broad scanner allowlists to silence a finding. False-positive suppressions must be narrow and demonstrably non-secret.

## 5. Proxy, forwarded-IP, and request-identity incident

`backend/api_middleware.py` controls request IDs, trusted proxy handling, access logging, and the bounded per-IP rate limiter. `TRUSTED_PROXY_CIDRS` is the explicit trust boundary for forwarded client identity.

If client identity is incorrect, attacker-controlled forwarding headers appear trusted, or request IDs are malformed/duplicated:

1. Treat unexpected proxy trust as a security boundary failure. Remove or rollback the configuration/deployment that introduced the incorrect trust relationship.
2. Compare the active proxy ranges with the intended infrastructure inventory. Do not widen `TRUSTED_PROXY_CIDRS` merely to make traffic pass.
3. Preserve representative request IDs, direct peer IPs, sanitized forwarding-chain metadata, and timestamps. Do not log authentication material.
4. Run the focused middleware regression suite through Backend Quality; locally, the relevant test is `backend/tests/test_api_middleware_adversarial.py`.
5. Restore traffic only after untrusted forwarding input is ignored and expected trusted-proxy chains resolve correctly.

Promote to SEV-1 if incorrect proxy trust could have bypassed an authorization, abuse-prevention, audit, or allowlist decision.

## 6. Rate-limit abuse or saturation

The middleware exposes bounded rate-limit state and telemetry. Relevant environment controls include `RATE_LIMIT_PER_MIN`, `RATE_LIMIT_BURST`, `RATE_LIMIT_MAX_BUCKETS`, and `RATE_LIMIT_BUCKET_TTL`.

1. Capture `/api/_telemetry` or equivalent operational telemetry before restarting, if doing so is safe and authorized. Record rate-limited totals, active bucket count, saturation rejections, and 4xx/5xx trends.
2. Verify that abuse is not being masked by a proxy/client-IP misconfiguration before changing limits.
3. Do not respond to saturation by setting unbounded state or disabling the limiter. Temporary tuning must remain positive, finite, and bounded.
4. Prefer upstream traffic controls for volumetric attacks while preserving application-level enforcement.
5. Run `backend/tests/test_api_middleware_adversarial.py` after any limiter or proxy change.
6. Roll back a new limiter/config change if it causes broad legitimate outage or weakens the security boundary.

## 7. Dependency or supply-chain alert

For a Python or JavaScript dependency alert:

1. Identify the package, installed version, affected runtime path, exploit prerequisites, and whether the vulnerable dependency ships to production.
2. Run or dispatch `.github/workflows/dependency-security.yml`. Preserve its Python and frontend SBOM/audit artifacts with the incident evidence.
3. For Python, reproduce with the pinned `pip-audit` policy from the workflow. For JavaScript, use the repository's `yarn audit` policy and `frontend/scripts/enforce-yarn-audit.js` rather than interpreting raw audit output ad hoc.
4. Patch or remove the affected dependency, regenerate lockfiles deterministically, and rerun dependency security plus canonical quality gates.
5. If a package, action, registry, or artifact source is suspected of compromise rather than an ordinary vulnerability, freeze releases and handle as a CI/supply-chain compromise.

Escalate to SEV-1 when a compromised dependency or build input is confirmed in a production release.

## 8. Compromised CI or workflow configuration

If a GitHub Actions workflow, action reference, build artifact, or CI credential may be compromised:

1. Stop releases and deployments sourced from the affected workflow until provenance is understood.
2. Revoke/rotate affected CI, registry, deploy, and signing credentials.
3. Preserve workflow YAML, run IDs, logs, artifacts, commit SHAs, actor information, and artifact hashes.
4. Run:

```bash
python backend/scripts/check_workflow_security.py
```

5. Verify action references remain immutable and workflow permissions are least-privilege.
6. Run the repository secret scan and `.github/workflows/dependency-security.yml`; regenerate SBOM evidence from a trusted commit.
7. Rebuild from a verified clean commit rather than reusing an artifact whose provenance is uncertain.

Do not restore deployment privileges until the credential boundary, workflow source, and produced artifacts are all accounted for.

## 9. Unsafe process execution, deserialization, or SAST finding

Run the dedicated repository controls:

```bash
python backend/scripts/check_process_safety.py
python backend/scripts/check_deserialization_safety.py
python backend/scripts/check_sast_security.py
python backend/scripts/check_js_process_alias_safety.py
```

If a finding is reachable in production, isolate the affected feature or rollback the introducing change. Preserve the triggering input in a safe, non-secret regression fixture. Do not weaken a scanner to make the build green; fix the unsafe path or add a narrow reviewed exception only when the behavior is demonstrably safe.

## 10. Availability or failed-deploy incident

1. Record the currently deployed and last-known-good commit/release identifiers.
2. Separate application failure from dependency, infrastructure, datastore, and proxy failure using health/telemetry evidence.
3. If a new release is causal and rollback is compatible with current state/schema, return to the last-known-good release.
4. If state restoration is required, use the environment's tested backup/restore procedure. This repository currently does not define a universal production datastore restore command; do not invent one during an incident.
5. After service restoration, run the relevant health checks and canonical quality/security gates against the exact commit that will remain deployed.

A rollback is containment, not root-cause resolution. Keep the incident open until the cause and forward fix are understood.

## 11. Evidence preservation

Preserve enough evidence for reconstruction without increasing exposure:

- UTC timeline, deployed commit/release IDs, workflow-run IDs, request IDs, sanitized client/proxy metadata, and operator actions;
- original logs and exported artifacts before rotation/deletion, with hashes when practical;
- dependency/SBOM outputs and exact lockfiles for supply-chain events;
- configuration names and whether they changed, but not secret values;
- screenshots only when structured/raw evidence cannot be retained safely.

Never rewrite original evidence in place. Work from copies, maintain timestamps, and document every destructive cleanup action.

## 12. Recovery exit criteria

An incident can move from active response to monitoring only when all applicable conditions are true:

- the exploit/trigger is contained and unauthorized access has stopped;
- exposed credentials are revoked or rotated;
- the production commit/release is explicitly identified and approved;
- relevant quality, security, secret, dependency, and adversarial tests pass;
- error/latency/rate-limit telemetry is stable at expected levels;
- required data or state validation is complete;
- evidence needed for review has been preserved;
- an owner and deadline exist for every deferred corrective action.

SEV-1 and SEV-2 incidents require a written post-incident review.

## 13. Post-incident review template

Record:

1. summary and severity;
2. customer/system impact and duration;
3. detection source and detection gap, if any;
4. UTC timeline from first known exposure/failure through recovery;
5. root cause and contributing factors;
6. containment and rollback decisions, including why they were safe;
7. evidence and validation performed;
8. what went well and what slowed response;
9. corrective actions with owners and deadlines;
10. regression test, policy, documentation, or monitoring changes that prevent recurrence.

## 14. Non-production drill

At least periodically, rehearse the read-only and verification portions of this runbook in a non-production environment:

```bash
bash scripts/quality-gates.sh
python backend/scripts/check_workflow_security.py
python backend/scripts/check_secret_hygiene.py
```

Also verify that authorized operators know how to dispatch the `Secret scanning` and `Dependency Security` workflows, locate their artifacts, identify the deployed commit, and execute the environment-specific rollback and backup/restore procedures. A drill is incomplete if those operational procedures are unknown or untested.
