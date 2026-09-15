# Security and production operations runbook

This is the first-response runbook for maintainers operating Skeleton and the
CodeDock/FastAPI surface in this repository. Prefer containment and preserved
evidence over speculative live fixes.

## Ownership and escalation

Until a dedicated rotation exists, the repository maintainer who merges a
production-affecting change is the default operational owner for that change.
Security findings that need code work must have a GitHub issue containing the
observed symptom, affected surface, severity/risk, reproduction evidence that
does not contain secrets, and the follow-up owner.

Never paste credentials, bearer tokens, private keys, raw user data, or full
sensitive subprocess output into an issue, pull request, CI log, or chat.

## Deployment topology and startup

The root Skeleton service is packaged by the root `Dockerfile` and listens on
port `8001` using:

```bash
uvicorn skeleton.api.server:create_app --factory --host 0.0.0.0 --port 8001
```

For local development the documented entry point is:

```bash
python -m skeleton run
```

The mobile CodeDock delivery surface is documented in `DELIVERY.md`; its
published client receives `EXPO_PUBLIC_BACKEND_URL` from the deployment/build
environment rather than a committed production URL.

Treat the public reverse proxy/load balancer as a separate trust boundary. Do
not expose internal admin/telemetry surfaces merely because the application
process is reachable.

## Environment and secrets

Start from `.env.example`; copy values into the deployment secret store or a
local untracked `.env`. Never commit the populated file. Important credential
classes include LLM/provider API keys, JWT signing material, payment/webhook
secrets, Forge HMAC keys/keyrings, and process-signing seed material.

`ALLOW_UNSAFE_CODE_EXECUTION` should remain false outside explicitly trusted
local/test environments. Configure `CORS_ORIGINS` narrowly for production.
Wildcard CORS is not a substitute for authentication or network controls.

Before deployment, check the committed repository for accidental credentials:

```bash
gitleaks git --redact --config=.gitleaks.toml
cd backend && python scripts/check_secret_hygiene.py
```

CI also runs `.github/workflows/secret-scanning.yml` across repository history.
Any allowlist change must be narrow and documented in `.gitleaks.toml`; never
allowlist a verified credential.

## Proxy trust, rate limiting, request IDs, WebSockets, and CORS

`backend/api_middleware.py` is fail-closed for proxy identity: forwarded client
addresses are trusted only when the direct peer matches an explicit
`TRUSTED_PROXY_CIDRS` network. An empty or malformed configuration disables
forwarded-header trust. Configure this to the actual final proxy hops, not to
broad internet ranges.

Operational rate-limit controls are:

- `RATE_LIMIT_PER_MIN`
- `RATE_LIMIT_BURST`
- `RATE_LIMIT_EXEMPT`
- `RATE_LIMIT_MAX_BUCKETS`
- `RATE_LIMIT_BUCKET_TTL`

Use exemptions only for addresses you operate. During abuse, lower throughput
and burst limits conservatively, monitor 429s and latency, and revert after the
incident with the same deployment mechanism used to apply the change. Do not
raise bucket limits simply to hide cardinality pressure.

Inbound `X-Request-Id` is accepted only in the middleware's bounded safe format;
otherwise a new server ID is minted. Use the request ID to correlate client
reports with access logs without treating it as identity or authorization.

HTTP proxy trust does not automatically make a WebSocket origin trustworthy.
WebSocket endpoints must independently validate authentication/origin and must
not infer client identity from forwarding headers unless the same trusted-hop
model is intentionally applied. Production CORS and WebSocket origin lists
should be explicit.

## Observability and first triage

Access logging is controlled by `ACCESS_LOG` and emitted through the
`api.middleware` logger. The CodeDock backend exposes `/api/_telemetry` for
request counters, latency percentiles, rate-limit state, evictions, saturation
rejections, and trusted proxy configuration. Deployment-platform stdout/stderr
is the authoritative log sink unless the deployment explicitly routes logs to
another store.

First triage sequence:

```bash
# Establish exactly what code is deployed.
git rev-parse HEAD
git status --short

# Re-run security/quality gates that do not mutate state.
cd backend
python scripts/check_secret_hygiene.py
python scripts/check_process_safety.py
python scripts/check_deserialization_safety.py
python scripts/check_sast_security.py
```

Then capture: incident start time in UTC, deployed commit, affected route or
job, request IDs, status-code distribution, 429/5xx changes, latency, proxy
path, and the smallest redacted log excerpt that establishes the failure.
Avoid restarting or deleting state until volatile evidence has been recorded
unless immediate containment requires it.

## Incident lifecycle

### 1. Detect and classify

Classify the event as at least one of: credential exposure, authentication or
authorization failure, proxy/client-identity spoofing, rate-limit bypass or
resource exhaustion, unsafe process execution, dependency/supply-chain event,
data integrity/loss, or availability failure. Record the blast radius and the
last known-good commit/deployment.

### 2. Contain

Prefer the smallest reversible control: disable the affected route/feature,
remove public reachability, revoke a credential, narrow proxy/CORS trust,
reduce rate limits, or roll back to a verified deployment. Do not merge an
unreviewed emergency workaround into `main` merely to match an ad-hoc
production change.

If subprocess output may contain tokens or secrets, stop the task that emits
it, restrict access to the log/artifact, rotate the credential as if exposed,
and only then produce redacted diagnostics. Do not copy the raw output into a
new channel.

If the reverse-proxy chain is uncertain, remove `TRUSTED_PROXY_CIDRS` (or set
it to the verified minimal hop set) so the application falls back to the
direct peer. Validate the real network path before restoring forwarded-client
trust.

### 3. Eradicate and recover

Patch the root cause with a regression test where practical. Run the relevant
CI/pre-commit gates. Restore service from a known-good build and configuration,
then re-enable traffic gradually while watching latency, 4xx/5xx, rate-limit
saturation, and logs for recurrence.

For data-bearing services such as MongoDB, verify a restorable backup before a
risky migration or cleanup. Runtime logs, caches, temp exports, generated
artifacts, and database snapshots belong outside normal Git history and should
follow the repository's canonical artifact/storage policy.

### 4. Review

Create or update a GitHub issue with the root cause, containment, permanent
fix, tests, owner, and any follow-up hardening. Record what detection failed or
was too slow. Close the incident only after credentials are rotated where
needed, affected deployments are replaced, and the regression path is covered.

## Credential leak rotation procedure

Deleting a secret from Git is **not** revocation. For any verified or plausible
credential leak:

1. Disable/revoke the exposed credential at its issuing provider first.
2. Create replacement material with the minimum required scope and lifetime.
3. Update the deployment secret store; do not commit the replacement.
4. Restart/redeploy consumers and confirm the old credential no longer works.
5. Audit provider/deployment logs from the earliest plausible exposure time.
6. Run Gitleaks plus the repository secret-hygiene gate again.
7. Decide separately whether coordinated Git-history rewriting is warranted;
   history cleanup reduces propagation but never substitutes for revocation.
8. Document the leak using redacted fingerprints/credential class only.

For signing/HMAC keyrings, preserve a deliberate overlap only when the protocol
requires verification of previously signed material; stop minting with the old
key immediately and remove it after the bounded verification window.

## Dependency and CI incidents

A failed Dependabot/security update is not permission to disable the gate.
Reproduce the failing check, isolate the minimum dependency/toolchain delta,
and either fix it or revert the update while opening a tracked follow-up.

If CI itself is compromised or unreliable, treat green results as untrusted:
stop merges that depend on the affected check, pin/review third-party actions,
restore the last trusted workflow revision, and rerun from a clean commit.
Do not use repeated reruns to convert a flaky red check into merge evidence;
follow `docs/MERGE_READINESS.md`.

## Emergency rollback checklist

- Identify the exact last known-good commit/image; do not roll back by memory.
- Preserve redacted evidence before destructive cleanup where possible.
- Rotate leaked credentials before restoring service with old code.
- Restore the smallest configuration surface necessary.
- Verify health plus one authenticated/authorized representative request.
- Verify request-ID/log correlation and proxy client identity.
- Watch 429, 4xx, 5xx, latency, and resource pressure after rollback.
- Open a follow-up issue before normal merge/deploy cadence resumes.
