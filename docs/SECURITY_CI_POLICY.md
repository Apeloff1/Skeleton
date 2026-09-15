# Security CI policy and operational runbook

This document is the repository-level security operations contract for Skeleton. It complements [`CI_REQUIRED_CHECKS.md`](CI_REQUIRED_CHECKS.md): that document defines the stable merge summary; this document defines what security controls are expected to protect, how failures are handled, and how exceptions, incidents, and credentials are managed.

## Security ownership

Repository maintainers own the security control plane. Any change that weakens a security gate, expands a token permission, widens a runtime/tool capability, introduces a new network/process/filesystem boundary, or changes release provenance must be reviewed as a security-sensitive change.

Security findings should be tracked in a focused issue or pull request with:

- the threatened boundary and affected component;
- whether exploitation requires untrusted input, repository write access, or deployment/runtime access;
- the control or regression test that prevents recurrence;
- any temporary exception, its owner, and its expiry;
- any external/admin-only action that source code cannot enforce.

Do not place live secrets, private exploit material, raw authorization headers, signed URLs, or credential-bearing logs in public issues, pull requests, artifacts, or CI output.

## Threat model

### Assets

The primary assets are source integrity, maintainer credentials, CI tokens, release artifacts and provenance, dependency integrity, runtime secrets, user/model/tool data, durable state, and the authority granted to agents/tools.

### Trust boundaries

1. **Pull request and event payload -> CI shell.** Titles, bodies, comments, refs, labels, workflow inputs, and other event fields are untrusted strings. They must not become shell code through direct expression interpolation.
2. **Repository source -> CI runner.** Workflows, actions, service/container images, dependency installers, and generated scripts can execute with repository context. References must be immutable where policy requires it, and token permissions must be least-privilege.
3. **Dependency and image supply chain -> build/release.** Lockfiles, dependency resolution, base images, build images, and third-party actions can introduce vulnerable or substituted code.
4. **Runtime request/model/tool input -> process, network, filesystem, and state.** Untrusted input must not widen sandbox capabilities, inject commands, escape allowed paths, trigger unsafe deserialization, or reach internal/network-sensitive targets through SSRF-like behavior.
5. **Build output -> release/deployment plane.** Artifacts must be attributable to reviewed source and expected workflows. Missing integrity/provenance evidence is a release blocker where the release policy requires it.
6. **Telemetry -> logs/artifacts.** Observability must preserve correlation and operational evidence without leaking sensitive payloads or secrets.

### Primary attacker goals

- execute attacker-controlled shell or process arguments in CI/runtime;
- obtain or exfiltrate repository/runtime credentials;
- bypass merge/release gates or downgrade a fail-closed security decision;
- substitute dependencies, actions, containers, or release artifacts;
- cross sandbox/tool capability boundaries;
- write or read outside intended filesystem/state scopes;
- abuse outbound requests to reach internal or metadata services;
- poison logs, telemetry, durable state, retrieval inputs, or release evidence.

## CI security controls

The repository keeps security controls split into focused workflows so failures identify a concrete boundary. The canonical merge summary remains **`CI/CD / Merge Readiness`** as described in [`CI_REQUIRED_CHECKS.md`](CI_REQUIRED_CHECKS.md).

Representative source-controlled controls include:

- `.github/workflows/ci.yml` and `.github/workflows/merge-readiness.yml` for the canonical merge gate and aggregate readiness contract;
- `.github/workflows/secret-scanning.yml` for repository/history credential scanning;
- `.github/workflows/dependency-review.yml`, `.github/workflows/dependency-security.yml`, and `.github/workflows/dependency-surface-guard.yml` for dependency/supply-chain checks;
- `.github/workflows/workflow-input-security.yml` for untrusted workflow-event/input shell-boundary checks;
- `.github/workflows/malware-gate.yml` for repository malware/IOC policy;
- `.github/workflows/artifact-policy.yml` for artifact/LFS policy;
- `.github/workflows/deployment-trust.yml` for deployment trust controls;
- `.github/workflows/provenance-policy.yml` and related release evidence workflows for provenance policy;
- backend security scripts/tests referenced by those workflows for static/process/deserialization/workflow policy enforcement.

Security scanners are expected to fail closed: scanner crashes, missing policy input, invalid configuration, or an inability to establish a required security property must not be converted into a successful result.

## Temporary exceptions

Security exceptions are exceptional, narrow, time-bounded, and reviewable. An exception must document:

- exact control being bypassed;
- exact path/component affected;
- reason the normal fix cannot land first;
- compensating control;
- named owner;
- linked tracking issue;
- explicit expiration date, normally no more than 30 days.

Do not use blanket path exclusions, repository-wide `continue-on-error`, unconditional `|| true`, or permanent allowlists to make a red security signal green. Expired exceptions must fail validation or be removed before further merge/release work.

Flaky-test quarantine is separately constrained by `.github/ci/flaky-quarantine.json`; a flaky label is not a security exception and must not suppress a deterministic security failure.

## Emergency merge override

An emergency override exists only for restoring repository availability or correcting an actively harmful production/release condition when the normal protected merge path cannot complete in time.

Required procedure:

1. Open or identify an incident/tracking issue and record the emergency reason.
2. Keep the change minimal; no unrelated cleanup, refactor, or feature work.
3. Preserve every security check that can still run. Never disable secret scanning or intentionally expose credentials to accelerate the override.
4. Record the exact commit, actor, skipped/failed check, and reason for bypass.
5. Obtain a second maintainer review when another maintainer is available; if not, record that the single-maintainer path was used.
6. Merge/deploy only the emergency correction.
7. Restore normal branch/ruleset enforcement immediately after the emergency action.
8. Run the canonical merge/readiness and release/security checks against the resulting branch state.
9. File follow-up work for every skipped control and close the incident only after normal enforcement is restored.

An override is not permission to make a security scanner pass artificially. The evidence must show what was bypassed and why.

## Credential rotation and revocation

Treat any credible secret finding as compromised until scope is established. Do not wait for proof of use before revoking a credential that was committed to Git history or emitted to a public artifact/log.

1. Identify credential type, owner/system, privileges, and environments affected.
2. Revoke or disable the exposed credential at the provider first.
3. Issue a replacement with the minimum required scope and lifetime.
4. Update the runtime/CI secret store; never commit the replacement to source.
5. Search current source, full Git history, workflow artifacts, logs, fixtures, examples, and documentation for additional copies.
6. Remove/redact exposed material where the hosting system supports it. History rewriting does **not** replace provider-side revocation.
7. Review provider audit logs for suspicious use during the exposure window.
8. Rotate dependent credentials when compromise could enable lateral access.
9. Add or improve a regression rule/fixture so the same credential pattern is caught earlier.
10. Record completion in the incident/tracking issue without pasting the secret itself.

## Incident response

### Triage

Classify the affected plane: credentials, CI/workflow, dependency/supply chain, runtime/API, agent/tool sandbox, storage/state, or release/deployment. Preserve timestamps, commit SHAs, workflow run IDs, artifact identifiers, package/image digests, and relevant provider audit events.

### Containment

- revoke exposed credentials and tokens;
- stop or disable a compromised release/deployment path;
- close or block the vulnerable input path;
- pin/rollback a substituted dependency, action, or image;
- remove excessive runtime/tool capabilities;
- preserve evidence before destructive cleanup where practical.

### Eradication and recovery

Land a focused fix with a regression test or policy fixture, rebuild from reviewed source, regenerate artifacts/provenance, and rerun the applicable security/merge/release gates. Do not reuse suspect artifacts merely because their source tree was later fixed.

### Post-incident

Document root cause, affected scope, evidence, corrective control, credential rotations, and any residual risk. Convert one-off detection logic into a maintained scanner/test when feasible.

## Sensitive output and redaction

Workflows and runtime diagnostics must not intentionally print:

- secret values or credentials;
- `Authorization`/cookie/session headers;
- signed URLs or bearer tokens;
- raw environment dumps;
- unredacted exception payloads that may contain request bodies, secrets, or user/model/tool content.

Prefer metadata such as error class, status category, correlation ID, bounded path/component identifiers, and redacted structured fields.

## Residual and admin-only risks

Some guarantees cannot be enforced by repository source alone:

- branch protection/rulesets must require the stable **`CI/CD / Merge Readiness`** check and prevent ordinary direct bypass;
- organization/repository settings determine who can change workflows, rulesets, secrets, environments, and release/deployment permissions;
- external registries/providers determine token revocation, audit retention, artifact immutability, and some provenance guarantees;
- self-hosted runner hardening, if introduced, requires host-level controls outside this repository.

Issues #127 and #540 track repository-admin enforcement and remaining security-hardening work. Source-controlled workflows should detect and document as much as possible, but they must not claim that an admin-only guarantee exists when repository settings do not enforce it.

## Security change acceptance

A security-hardening pull request should state:

- threat closed;
- files/control plane changed;
- regression coverage added;
- whether merge/release enforcement changes;
- residual/admin-only risk.

A control is considered complete only when the implementation and its regression evidence exist on the protected branch and any required external/admin enforcement is actually configured.