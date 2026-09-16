# Security adversarial regression matrix

This document defines the minimum adversarial regression corpus for the repository-wide hardening work tracked by #540.

The matrix is intentionally implementation-neutral: a regression should exercise the production guard or canonical scanner rather than merely assert that a fixture exists.

| Surface | Adversarial case | Required assertion |
|---|---|---|
| Path handling | `../` traversal, absolute paths, mixed separators, encoded traversal | Reject or normalize before filesystem access; never escape the allowed root |
| Archives | zip-slip names, absolute archive members, excessive expansion | Reject unsafe members and enforce bounded extraction |
| Network | loopback, RFC1918, link-local/metadata addresses, non-HTTP(S) schemes, redirects | Reject disallowed destinations and unsafe redirects |
| Commands | shell metacharacters, newline injection, option injection | Treat untrusted values as data; no shell interpretation |
| Deserialization | pickle/object payloads, unsafe YAML tags, malformed structured input | Reject unsafe object construction and malformed input |
| Secrets | API keys, bearer tokens, signed URLs, high-entropy credentials in fixtures/logs | Do not emit credentials into logs, artifacts, prompts, or comments |
| CI | untrusted event/ref/input interpolation, mutable action/container references | Canonical workflow-security gates fail closed |
| Scanner failure | missing input, malformed input, unavailable dependency, parser error | Scanner exits non-zero or otherwise reports an explicit failure; never silently passes |

## Evidence requirements

For each newly covered case, the focused test should record:

1. the production entry point under test;
2. the malicious input class;
3. the expected fail-closed behavior;
4. the regression test name;
5. the canonical CI job that executes it.

A fixture alone is not security evidence. A passing test must demonstrate that the relevant production boundary rejects, contains, or safely transforms the adversarial input.

## Scope boundary

This matrix does not claim that every listed control is already implemented. It is the regression target for the remaining security-audit work. Missing production controls should result in a focused remediation PR rather than weakening the test or marking the case as satisfied by documentation alone.
