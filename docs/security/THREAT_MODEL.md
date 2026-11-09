# Skeleton Threat Model

Status: maintained operational security model for the canonical `main` architecture.

## Security objectives

Protect code, credentials, provider/model boundaries, durable state, user-controlled inputs, CI/CD trust, release artifacts, and telemetry against unauthorized disclosure, modification, execution, privilege expansion, or silent integrity loss.

Security-sensitive paths should fail closed when provenance, authorization, scanner execution, or policy evaluation cannot be established.

## Trust boundaries

### Repository and CI/CD

Untrusted inputs include pull-request content, refs, commit/issue metadata, workflow event payloads, dependency metadata, container images, and third-party Actions.

Primary threats include workflow command injection, unsafe event interpolation, mutable third-party execution, token over-privilege, credential persistence, privileged/host-sensitive containers, dependency compromise, and artifact tampering.

Expected controls: immutable Action/container references, least-privilege workflow permissions, checkout without persisted credentials where applicable, no untrusted-code execution through `pull_request_target`, and fail-closed workflow/dependency/secret/malware/artifact/provenance gates.

### API and ingress

Untrusted inputs include bodies, headers, content types, paths, identifiers, uploaded content, and client-controlled metadata.

Primary threats include oversized or malformed requests, authn/authz bypass, traversal, denial of service through unbounded work/state, and leakage of internal errors or sensitive telemetry.

Expected controls: explicit limits and validation, deny-by-default authorization, bounded rate/state handling, normalized paths, generic external errors, and redacted structured telemetry.

### Provider/model runtime

Untrusted inputs include prompts, provider responses, streaming events, tool proposals, model-generated code/text, and remote failures.

Primary threats include malformed stream state, retry amplification, duplicate side effects, capability escalation through model output, and credential/error leakage across provider boundaries.

Expected controls: provider-neutral contracts, bounded retries and total deadlines, no restart after partial stream emission, sanitized failures, and explicit capability checks before side effects.

### Agents and tools

Model output is not an authority boundary.

Primary threats include command injection, unsafe subprocess execution, filesystem escape, dynamic import/eval abuse, sandbox widening, and tool side effects without a grant.

Expected controls: deny-by-default capability grants, typed/validated tool arguments, constrained process/filesystem surfaces, auditable capability-sensitive operations, and adversarial regression tests.

### Retrieval, memory, and durable state

Untrusted inputs include ingested documents, metadata, embeddings, retrieval results, checkpoints, and resumed state.

Primary threats include poisoned retrieval content, provenance loss, unbounded caches, duplicated durable transitions, stale ownership, and cross-request contamination.

Expected controls: provenance-preserving retrieval contracts, bounded retention, deterministic durable revisions, idempotent retries, ownership/lease rules, and recovery tests.

### Outbound network

Any URL or host influenced by user/model input is untrusted.

Primary threats include SSRF to loopback/link-local/private/metadata targets, redirect bypass, DNS-rebinding assumptions, unbounded responses, and credential forwarding to unrelated origins.

Expected controls: restricted schemes/destinations, redirect revalidation, explicit timeouts and size limits, and origin-scoped credentials.

### Dependencies, containers, and release artifacts

Primary threats include vulnerable or malicious dependencies, mutable images, tampered outputs, absent SBOM/provenance evidence, and secrets baked into layers/artifacts.

Expected controls: dependency review/audit, immutable image digests, container vulnerability scanning, SBOM/provenance generation and validation, artifact-policy enforcement, and runtime secret injection.

## Sensitive assets

- repository/workflow credentials;
- provider/API keys and auth tokens;
- user/private data entering API, memory, logs, traces, or artifacts;
- durable run/checkpoint state;
- release artifacts, provenance, and SBOM evidence;
- policy configuration defining tool, CI, and release permissions.

## Security invariants

1. Untrusted pull-request code must not obtain write-capable repository credentials merely by being opened.
2. Model-generated output cannot grant itself new capabilities.
3. Secrets and sensitive payloads must be redacted from normal logs and errors.
4. Security scanners must fail closed when they cannot complete reliably.
5. Retries must be bounded and must not duplicate durable side effects.
6. Release evidence must be traceable to the source revision and declared build inputs.
7. Mutable third-party execution dependencies are not accepted where immutable references are required by policy.

## Residual risks

Some controls are outside repository code and require GitHub or deployment administration. These include branch protection/required-check enforcement, emergency bypass governance, external secret-store configuration, production network egress policy, and runtime container security settings.

Repository-specific status and externally owned gaps are tracked in `docs/security/SECURITY_STATUS.md`.

## Review triggers

Review this model when a new externally reachable interface is added; a tool gains subprocess/filesystem/browser/network/secret access; a provider/runtime changes; CI gains new permissions or trigger classes; build/release infrastructure changes; or an incident invalidates a documented assumption.
