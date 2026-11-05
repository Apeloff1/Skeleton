# privacy — production laptop AI assurance

The `privacy` source-controlled casebook contains 14 independently named
inputs. Each is executed against the real Python validator or state machine,
not a fake model response. No casebook may directly invoke tools, external
providers, model installation, a hardware benchmark or branch promotion.

## Cases and security intent

- **00_valid** — accept. Only public metadata is emitted.
- **01_redacted** — no_leak. Private prompt must never escape telemetry permitlist.
- **02_redacted** — no_leak. Private token must never escape telemetry permitlist.
- **03_redacted** — no_leak. Private password must never escape telemetry permitlist.
- **04_redacted** — no_leak. Private bearer must never escape telemetry permitlist.
- **05_redacted** — no_leak. Private session_secret must never escape telemetry permitlist.
- **06_redacted** — no_leak. Private private_path must never escape telemetry permitlist.
- **07_redacted** — no_leak. Private memory_text must never escape telemetry permitlist.
- **08_redacted** — no_leak. Private authorization must never escape telemetry permitlist.
- **09_redacted** — no_leak. Private tool_args must never escape telemetry permitlist.
- **10_redacted** — no_leak. Private user_input must never escape telemetry permitlist.
- **11_redacted** — no_leak. Private source_passage must never escape telemetry permitlist.
- **12_invalid_shape** — reject. Non-object telemetry cannot be accepted.
- **13_bad_status** — reject. Public status must be a bounded string.

## Execution and independent evidence

Review every literal payload and expected refusal. Execute
`python -m unittest skeleton.testing.test_laptop_qualification_privacy`
in the canonical checkout at the exact current head. Tests fail on missing
case files, unknown source fields, duplicate case IDs, unexpected acceptance,
missing redaction or exception masking.

These 1 positive, 2 expected-denial and
11 no-private-output cases only prove input contracts; separate
live GGUF-native E2E, authenticated HTTP, durable restart, real host capacity,
clean laptop installation, model rights, exact-head CI and independent review
must all be completed before a release claim is permitted.

## Maintainer invariants

Do not replace model inference with a deterministic fake in production.
Do not treat model text as an operator command, provider secret, trusted
retrieval authority, memory consent or verification signature. A rejected
case must not be compensated for by weakening an existing fail-closed gate.
