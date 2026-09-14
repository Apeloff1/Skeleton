# Security Incident Response Runbook

This runbook covers the security controls introduced by the request-boundary and supply-chain hardening program. Preserve evidence first, contain exposure second, then restore service from verified inputs.

## First 15 minutes

1. Record the UTC detection time, affected environment, current release/version, source commit, and reporter.
2. Preserve relevant application/audit logs and CI evidence before rotating or deleting anything.
3. Stop further deployment of the affected revision.
4. If credentials may be exposed, revoke/rotate them immediately after preserving enough evidence to establish scope. Never paste suspected secret values into issues or CI logs.
5. If active exploitation is suspected, reduce external exposure with the narrowest reversible control available: disable the affected endpoint/tool, reduce trusted proxy ranges, revoke a credential, or roll back to the last verified release.

## Suspected credential exposure

- Treat a confirmed committed credential as compromised even if the repository is private or the commit was later deleted.
- Revoke/rotate at the provider first; history rewriting does not invalidate an already copied secret.
- Identify all systems, workflows, users, and environments that could use the credential.
- Search current source, generated artifacts, CI logs, issue text, release assets, and reachable history for additional copies.
- Replace credentials using the platform's secret store; do not commit replacement values.
- Validate that `check_secret_hygiene.py` and platform secret scanning no longer report the material.
- Record rotation time and impacted services in the incident issue without recording the secret itself.

## Proxy / client-IP trust incident

Symptoms include unexpected rate-limit bypasses, audit events attributed to arbitrary public IPs, or direct clients influencing `X-Forwarded-For` identity.

Containment:

- Review `TRUSTED_PROXY_CIDRS`; restrict it to actual ingress/load-balancer networks.
- In production, malformed CIDRs must stop startup rather than broaden trust.
- Confirm direct clients cannot reach an internal listener that assumes a trusted proxy is in front of it.
- Inspect rate-limit/audit telemetry for high-cardinality identity rotation.

Verification:

- Run `test_client_ip_security.py`, `test_rate_limit_state_security.py`, and `test_security_parser_fuzz.py`.
- Verify the deployed reverse proxy overwrites, rather than appends untrusted client-supplied forwarding headers according to the intended architecture.

## Request-body / HTTP framing incident

Symptoms include memory pressure, oversized uploads reaching handlers, or inconsistent parsing between proxy and application.

Containment:

- Reduce `CODEDOCK_MAX_BODY_MB` if necessary.
- Reject traffic paths bypassing the normal ingress.
- Confirm no intermediary permits conflicting `Content-Length` and `Transfer-Encoding` framing.

Verification:

- Run `test_size_limit_security.py` and `test_security_middleware_hardening.py`.
- Confirm streamed/chunked payloads are counted cumulatively and rejected at the configured cap.

## Rate-limit resource exhaustion

Symptoms include rising memory associated with rate-limit buckets or unusual high-cardinality client identities.

- Inspect active bucket and eviction telemetry.
- Verify `RATE_LIMIT_MAX_BUCKETS` / `CODEDOCK_RATE_LIMIT_MAX_BUCKETS` and TTL values are sane.
- Do not respond by disabling throttling globally.
- If traffic is malicious, add upstream controls while preserving the application-level bounded limiter.
- Run the bounded-state/concurrency regression suite before redeployment.

## SSRF / outbound fetch incident

If a scraper or outbound connector is suspected of accessing internal or attacker-controlled endpoints:

- Disable the affected fetch path or reduce its host allowlist.
- Review destination scheme, hostname, port, redirect behavior, DNS resolution, and response-size controls.
- Block cloud metadata, loopback, private/link-local, and non-approved destinations at network boundaries where possible.
- Preserve outbound request logs without storing credentials or sensitive response bodies.
- Run `test_live_scraper_security.py` before restoring the path.

## CI / supply-chain incident

Examples include a compromised third-party action, unexpected workflow permission change, malicious dependency update, or altered build artifact.

Containment:

- Stop affected workflows/releases.
- Identify the first affected source commit and workflow run.
- Compare workflow action SHAs with known-good immutable revisions.
- Revoke write-capable workflow credentials if compromise is plausible.
- Rebuild from a clean checkout only after the dependency/workflow source is trusted again.

Verification:

- Run `check_workflow_security.py` and `check_dependency_policy.py`.
- Run the OSV dependency audit.
- Generate a fresh SBOM and build provenance record.
- Compare `SHA256SUMS`, source SHA, manifest hashes, and artifact hashes with the expected release evidence.

## Unsafe code execution / deserialization incident

If untrusted input may have reached process execution, `eval`/`exec`, unsafe object deserialization, or disabled TLS/JWT verification:

- Disable the affected route/tool and preserve input/audit evidence.
- Treat the host/container as potentially compromised if arbitrary code execution was possible.
- Rotate credentials accessible to that execution environment.
- Rebuild/redeploy from a trusted base rather than attempting to clean an untrusted runtime in place.
- Run process-safety, deserialization-safety, and SAST gates before restoration.

## Rollback

A rollback target must be a known source commit with passing required checks and known build provenance. Prefer immutable artifacts already produced from that commit. After rollback, confirm health and security telemetry before reopening full traffic.

Do not roll back to a version with a known equal-or-higher severity vulnerability merely to restore availability unless the incident commander explicitly accepts and documents that tradeoff.

## Evidence preservation

Preserve, as applicable:

- exact source/head SHA and base SHA;
- CI run/job identifiers;
- `security-build-evidence` artifact;
- deployment/release identifier and artifact checksums;
- sanitized application/audit logs;
- dependency lock/manifests;
- relevant configuration names and safe values (never secret contents);
- timeline of containment and recovery actions.

## Recovery exit criteria

Recovery is complete only when the vulnerable path is fixed or disabled, exposed credentials are rotated, affected systems are rebuilt or verified, the current head passes required security/CI gates, security evidence is retained, and a follow-up issue captures root cause plus prevention work.
