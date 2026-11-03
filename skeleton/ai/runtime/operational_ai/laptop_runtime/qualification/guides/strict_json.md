# strict json — production laptop AI assurance

The `strict_json` source-controlled casebook contains 14 independently named
inputs. Each is executed against the real Python validator or state machine,
not a fake model response. No casebook may directly invoke tools, external
providers, model installation, a hardware benchmark or branch promotion.

## Cases and security intent

- **00_valid** — accept. Explicit caller-owned bounded input.
- **01_attack** — reject. Refuse adversarial strict_json variant 1.
- **02_attack** — reject. Refuse adversarial strict_json variant 2.
- **03_attack** — reject. Refuse adversarial strict_json variant 3.
- **04_attack** — reject. Refuse adversarial strict_json variant 4.
- **05_attack** — reject. Refuse adversarial strict_json variant 5.
- **06_attack** — reject. Refuse adversarial strict_json variant 6.
- **07_attack** — reject. Refuse adversarial strict_json variant 7.
- **08_attack** — reject. Refuse adversarial strict_json variant 8.
- **09_attack** — reject. Refuse adversarial strict_json variant 9.
- **10_attack** — reject. Refuse adversarial strict_json variant 10.
- **11_attack** — reject. Refuse adversarial strict_json variant 11.
- **12_attack** — reject. Refuse adversarial strict_json variant 12.
- **13_attack** — reject. Refuse adversarial strict_json variant 13.

## Execution and independent evidence

Review every literal payload and expected refusal. Execute
`python -m unittest skeleton.testing.test_laptop_qualification_strict_json`
in the canonical checkout at the exact current head. Tests fail on missing
case files, unknown source fields, duplicate case IDs, unexpected acceptance,
missing redaction or exception masking.

These 1 positive, 13 expected-denial and
0 no-private-output cases only prove input contracts; separate
live GGUF-native E2E, authenticated HTTP, durable restart, real host capacity,
clean laptop installation, model rights, exact-head CI and independent review
must all be completed before a release claim is permitted.

## Maintainer invariants

Do not replace model inference with a deterministic fake in production.
Do not treat model text as an operator command, provider secret, trusted
retrieval authority, memory consent or verification signature. A rejected
case must not be compensated for by weakening an existing fail-closed gate.
