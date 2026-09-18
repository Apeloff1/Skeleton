# Security Policy

## Reporting a vulnerability

Do not publish exploit details, credentials, tokens, private data, or proof-of-concept material in a public issue.

Preferred path:

1. Use GitHub's private vulnerability-reporting / Security Advisory flow for this repository when it is available.
2. If private reporting is unavailable, open a minimal public issue stating that you need a private security contact. Do not include the vulnerability details in that issue.
3. Include the affected component and revision, impact, reproduction preconditions, and a minimal safe reproducer once a private channel is established.

Repository maintainers should triage reports, preserve evidence, contain active exposure, rotate or revoke affected credentials, and track remediation through `docs/SECURITY_INCIDENT_RESPONSE.md`.

## Scope

Security-sensitive surfaces include GitHub Actions and release automation; provider/runtime and agent/tool boundaries; API authentication, authorization, request handling, and rate limits; retrieval, state, storage, and artifact handling; dependency/container supply chain; and secret handling/telemetry redaction.

The maintained threat model is `docs/security/THREAT_MODEL.md`. The current control map and residual-risk register are in `docs/security/SECURITY_STATUS.md`.

## Disclosure

Coordinate disclosure with maintainers after a fix or mitigation is available. Never include live secrets or unrelated private data in reports, tests, or examples.
