# Production Security & Incident-Response Runbook

Status: operational contract for Skeleton production-like deployments.

Owner: repository maintainers / on-call operator.

Issue: #128.

## 1. Purpose and operating rule

This runbook defines the fail-closed response path for security, reliability,
and deployment incidents affecting Skeleton. It is intentionally provider- and
host-neutral: replace deployment-specific commands only in the deployment
wrapper, not in the incident decision logic.

The governing rule is **contain first, preserve evidence second, recover from a
known-good state third**. Do not destroy logs, rotate away the only copy of a
suspect credential, force-push history, or “fix forward” on an unverified
production host before preserving enough evidence to reconstruct what happened.

Production recovery is complete only when:

1. the triggering condition is contained;
2. affected credentials or trust material are rotated where required;
3. the recovered build is tied to a known source commit;
4. required security/reliability checks pass on that commit;
5. data/state integrity has been verified; and
6. follow-up actions have owners and deadlines.

## 2. Severity and escalation

Use the highest applicable severity.

| Severity | Examples | Immediate action |
|---|---|---|
| SEV-1 | confirmed credential exfiltration, active unauthorized mutation, compromised CI/release path, destructive data loss, remote-code-execution evidence | freeze deploys; isolate affected credentials/services; preserve evidence; invoke rollback/rebuild from known-good source |
| SEV-2 | sustained rate-limit bypass/abuse, trusted-proxy misconfiguration, dependency exploit with plausible exposure, repeated integrity failures | stop risky changes; constrain traffic/capabilities; validate trust boundaries; prepare rollback |
| SEV-3 | contained CI failure, non-exploitable dependency alert, isolated operational regression, degraded but trustworthy service | keep service under observation; remediate through normal PR + required checks |

Escalate one level when scope is unknown, evidence is incomplete, or a control
that should fail closed is observed failing open.

## 3. First 15 minutes

### 3.1 Declare and freeze

Record:

- UTC declaration time;
- incident commander/operator;
- suspected start time;
- affected environment(s), service(s), branch/commit, and credentials;
- current symptoms and the evidence that triggered the incident;
- last known-good commit/release.

For SEV-1/SEV-2, freeze non-essential deploys and repository mutations until the
recovery commit and blast radius are understood.

### 3.2 Preserve evidence

Preserve before cleanup:

- application, proxy, platform, and audit logs covering the suspected window;
- deployed image/artifact digests and source commit SHA;
- relevant GitHub Actions run IDs and workflow revisions;
- dependency lockfiles/manifests used by the deployed build;
- configuration *names and hashes* needed to reproduce the state.

Do **not** paste secrets into incident notes. Record credential identifiers,
provider-side event IDs, hashes, and rotation timestamps instead.

When possible, copy evidence to read-only storage before restart, rollback, or
credential rotation. Record who collected it and when.

### 3.3 Contain

Choose the least destructive containment that stops further harm:

- revoke/rotate a credential;
- disable a provider/integration;
- restrict ingress to a known proxy/network path;
- reduce an exposed feature/capability set;
- pause deployments/workflows;
- roll back to a known-good immutable artifact;
- take the affected service out of rotation.

If you cannot prove the current deployment is trustworthy, prefer rebuilding
from a known-good source commit over repairing the running host in place.

## 4. Safe startup and configuration validation

Before restoring traffic to a changed or rebuilt deployment:

1. Confirm the intended source commit and working tree are clean.
2. Confirm production secrets are injected by the deployment environment and
   are not present in the repository, image layers, logs, or generated files.
3. Validate security-sensitive configuration with the repository's fail-closed
   parsing rules. Empty, malformed, ambiguous, non-finite, or out-of-range
   values are incident conditions, not values to coerce silently.
4. Confirm trusted proxy CIDRs represent only actual trusted ingress peers.
5. Confirm request/body/rate-limit limits are positive and bounded.
6. Confirm the deployment is using the expected dependency lock/manifests and
   image/artifact digest.
7. Run the relevant repository gates listed in section 12 before promotion.

Never bypass a required gate by setting a permissive environment variable or by
removing the failing check from the workflow during incident recovery.

## 5. Suspected secret or credential exposure

Treat a credential as exposed when it appears in repository history, CI output,
logs available to unintended readers, an artifact/image layer, a public issue,
or a compromised host.

### Containment

1. Revoke or disable the exposed credential at the provider first when doing so
   will not destroy evidence needed for attribution.
2. Create a replacement credential with the minimum required scope.
3. Update the deployment secret store; never commit the replacement.
4. Restart/redeploy only the components that need the new credential.
5. Verify old credentials are rejected and the new credential works only in its
   intended scope.

### Repository response

Run the local hygiene gate from a clean checkout:

```bash
(cd backend && python scripts/check_secret_hygiene.py)
```

Then run the immutable secret-scanning workflow and inspect the affected commit
range. Relevant controls:

- [Secret Scanning workflow](../.github/workflows/secret-scanning.yml)
- [Dependency Security workflow](../.github/workflows/dependency-security.yml)
- [secret hygiene gate](../backend/scripts/check_secret_hygiene.py)
- [.gitleaks.toml](../.gitleaks.toml)

If a real secret entered Git history, rotation is mandatory even if the file is
subsequently deleted. History rewriting is a separate cleanup decision and is
not a substitute for credential revocation.

### Exit criteria

- old credential revoked;
- replacement scoped and deployed;
- scans are clean or documented false positives are narrowly allowlisted;
- no replacement value exists in Git/CI logs/artifacts;
- affected access logs reviewed for abuse.

## 6. Rate-limit abuse or identity churn

Symptoms include sustained 429s, bucket saturation, many unique client
identities, or evidence that forwarded headers are changing limiter identity.

1. Confirm the direct peer identity and whether it is a configured trusted
   proxy. Do not trust `X-Forwarded-For` from arbitrary clients.
2. Confirm route-boundary matching is exact-or-child, not raw prefix matching.
3. Inspect rate-limit saturation/eviction telemetry and request-ID correlation.
4. If high-cardinality traffic is exhausting state, constrain ingress at the
   outer proxy/firewall before increasing in-process limits.
5. Do not “fix” saturation by evicting active buckets and granting fresh bursts.
6. Re-run focused backend security regressions before restoring normal limits.

Relevant controls:

- [Backend Quality workflow](../.github/workflows/backend-quality.yml)
- [CI/CD workflow](../.github/workflows/ci.yml)

Escalate to SEV-1 if the limiter or identity resolver can be bypassed to reach a
sensitive operation without the intended control.

## 7. Trusted-proxy or ingress misconfiguration

A malformed or overly broad proxy trust configuration can turn attacker-supplied
headers into trusted identity.

1. Remove the affected instance from public traffic if client identity is used
   for authorization, throttling, or audit decisions.
2. Compare configured trusted CIDRs against the actual immediate ingress peers.
3. Treat unknown/malformed chains as untrusted; do not pick a convenient header
   value to keep the service online.
4. Verify direct/untrusted clients cannot rotate identity through forwarded
   headers.
5. Restore traffic only after trusted/untrusted and malformed-chain regression
   tests pass.

When the correct proxy topology is uncertain, run without forwarded-header trust
until the topology is verified.

## 8. Dependency or supply-chain alert

Use this path for Dependabot/advisory findings, compromised upstream packages,
container-base alerts, or suspicious build dependencies.

1. Identify the exact package/image, version/digest, lockfile, and deployed
   artifact(s) that contain it.
2. Determine exploitability in Skeleton's reachable code path; do not downgrade
   severity merely because the vulnerable symbol is not obviously imported.
3. If exploitation is plausible, stop affected deploys and move to SEV-2/SEV-1.
4. Patch through a normal reviewed PR with immutable action pins and explicit
   permissions preserved.
5. Rebuild from a clean checkout; do not reuse suspect build caches.
6. Verify the resulting artifact digest and dependency manifests.

Relevant controls:

- [Dependency Security workflow](../.github/workflows/dependency-security.yml)
- [Deployment Trust workflow](../.github/workflows/deployment-trust.yml)
- [workflow security gate](../backend/scripts/check_workflow_security.py)

## 9. Suspected CI or workflow compromise

Signals include unexplained workflow edits, action pin changes, unexpected write
permissions, artifact mismatch, credential persistence, or a release whose
provenance cannot be tied to the expected source.

1. Freeze release/deploy workflows.
2. Preserve the suspect workflow files, run IDs/logs, commit SHAs, artifact
   digests, and actor/event metadata.
3. Revoke credentials or tokens exposed to the suspect job where applicable.
4. Compare workflow/action revisions against the last known-good commit.
5. Re-run workflow-security checks from a trusted clean checkout.
6. Rebuild artifacts from known-good source without reusing the suspect runner
   workspace or caches.
7. Re-enable automation only after least-privilege permissions, immutable action
   pins, and artifact/source correspondence are verified.

Local check:

```bash
(cd backend && python scripts/check_workflow_security.py)
```

A green job produced by an untrusted workflow revision is not evidence of
safety. Validate the workflow definition itself first.

## 10. Data/state corruption, backup, and restore

For durable application state, distinguish authoritative state from rebuildable
caches/artifacts.

### Before restore

- stop writers or place the service in a read-only/maintenance state;
- capture the corrupt/current state for later analysis when safe;
- identify the recovery point and verify its timestamp/hash;
- document expected data loss window before proceeding.

### Restore

1. Restore into an isolated non-production location first where practical.
2. Run schema/version/integrity checks before attaching application traffic.
3. Compare expected record counts/checkpoints/hashes against the recovery plan.
4. Promote the restored state only after the application can read it without
   mutation errors.
5. Re-enable writers gradually and watch error/latency/integrity telemetry.

Never overwrite the only known backup during validation. A backup that has not
been restored successfully in a drill is an unverified backup.

## 11. Deployment rollback

Rollback when any of these is true:

- the active build cannot be tied to an expected source commit/digest;
- a security boundary is failing open;
- a new release is causing destructive or compounding state mutation;
- recovery by configuration change would require bypassing a required guard;
- blast radius is increasing faster than root-cause analysis can converge.

Rollback target requirements:

- known source commit/release;
- known dependency/artifact provenance;
- compatible state/schema or an explicit migration rollback plan;
- required checks were green for the target or are re-run before promotion.

After rollback, keep the incident open until the triggering condition is
understood. “Service recovered” and “incident resolved” are separate events.

## 12. Required checks before recovery promotion

Select the checks matching the incident, but SEV-1 recovery should run the full
relevant set.

- [CI/CD](../.github/workflows/ci.yml): application lint/test/build baseline.
- [Backend Quality](../.github/workflows/backend-quality.yml): backend and
  security regressions.
- [Dependency Security](../.github/workflows/dependency-security.yml): Python,
  JavaScript, and dependency policy checks.
- [Deployment Trust](../.github/workflows/deployment-trust.yml): deployment
  trust/provenance controls.
- [Secret Scanning](../.github/workflows/secret-scanning.yml): immutable secret
  scan.
- [Route Coverage](../.github/workflows/route-coverage.yml): governed backend
  route inventory.
- [Product Convergence](../.github/workflows/product-convergence.yml): selected
  cross-product contracts.

Security-specific local gates:

```bash
(cd backend && python scripts/check_process_safety.py)
(cd backend && python scripts/check_deserialization_safety.py)
(cd backend && python scripts/check_sast_security.py)
(cd backend && python scripts/check_workflow_security.py)
(cd backend && python scripts/check_secret_hygiene.py)
```

Do not interpret cancellation, skipped jobs, missing required checks, or a
workflow that never triggered as success.

## 13. Non-production drills

Run these drills after material changes to the related controls and at least
periodically for production-like deployments.

### Drill A — credential exposure

- inject a fake test credential pattern in an isolated branch/fixture;
- prove local/CI secret scanning detects it;
- remove the fixture and confirm clean recovery;
- rehearse provider-side rotation using a non-production credential.

### Drill B — proxy spoof / limiter pressure

- send requests from an untrusted direct client with changing forwarded headers;
- confirm client identity does not rotate;
- generate bounded high-cardinality traffic and confirm state remains bounded
  and new identities fail closed at saturation.

### Drill C — restore

- restore the latest backup into an isolated environment;
- verify integrity/schema/readability;
- measure recovery point and time;
- record any manual step not represented in deployment automation.

### Drill D — CI compromise

- use a disposable branch to intentionally violate workflow policy (for example,
  a floating third-party action ref or excess permission);
- prove the workflow-security gate rejects it;
- delete the disposable branch after evidence is recorded.

Record drill date, commit, operator, result, and follow-up issue. A failed drill
is a reliability finding, not a documentation-only problem.

## 14. Post-incident review

Within the next normal engineering cycle, record:

- timeline in UTC;
- initiating condition and contributing factors;
- why existing controls did or did not prevent/detect it;
- exact affected source/releases/data/credentials;
- containment and recovery actions;
- evidence retained and retention location;
- customer/user impact where applicable;
- permanent corrective actions with issue links and owners;
- one regression test or automated control for every reproducible failure mode
  where technically feasible.

Avoid attributing root cause to an individual action when the system permitted a
single action to produce the failure. Prefer controls that make the unsafe state
hard or impossible to reach.

## 15. Incident record template

```text
Incident ID:
Severity:
Declared (UTC):
Commander/operator:
Affected environment/service:
Suspected start (UTC):
Last known-good commit/release:
Observed symptoms:
Evidence preserved:
Containment actions:
Credentials rotated/revoked:
Rollback/rebuild target:
Validation checks and run links:
Recovery time (UTC):
Known data loss window:
Root cause / contributing factors:
Follow-up issues + owners:
Resolution time (UTC):
```

## 16. Runbook maintenance

`scripts/check_ops_runbook.py` is the executable documentation contract for this
file. CI verifies required sections and repository-local control references.
When security workflows or gate paths move, update the runbook and validator in
the same PR.
