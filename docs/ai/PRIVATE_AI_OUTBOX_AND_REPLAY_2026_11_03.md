# Private AI outbox and replay — operational connector boundary

This subsystem exports **only policy-validated AI metadata** from the native
SQLite execution/flight journals into immutable, owner-only on-device files.
It intentionally does not execute generated tools, trigger outbound network
requests, send private prompts, create model outputs, or claim release readiness.

## Authority and persistence

1. Inference code commits its authoritative result, audit entry and SQLite
   outbox event in one `BEGIN IMMEDIATE` transaction. No external delivery
   occurs inside that transaction.
2. An independently authorized operator opens a private spool under a
   descriptor-anchored `0700` directory. The spool has an immutable `0600`
   owner record for tenant, subject, model digest and tokenizer digest.
3. The publisher rejects unreviewed JSON keys, payload types and transition
   schemas. Only known `ai_flight` and `ai_turn` observations are exportable.
4. The publisher writes `0600` immutable, SHA-bound receipts with exclusive
   create, then fsyncs the receipt and its directory, and **only then** acks
   the source outbox row. An interrupted post-publish/pre-ack operation can
   replay the exact existing bytes without repeating inference.
5. Independent consumers use the authoritative monotonically increasing
   SQLite event sequence. A missing file after ack or a mismatched payload
   closes the boundary; there is no synthesized event or gap erasure.
6. A bounded local operator daemon can continuously drain the spool. It has
   no HTTP server, plugin, model API or remote network sink, and stops on
   corruption rather than guessing whether a write succeeded.

## Operator

Create the state directory through the existing verified first-install path.
Create a separately private spool directory (mode `0700`) beneath a trusted
parent; no implicit mkdir or unowned spool adoption takes place.

```
python -m skeleton.ai.runtime.operational_ai.transport.flight.outbox_delivery.cli \
  --state-dir "$PRIVATE_STATE" --spool-dir "$PRIVATE_SPOOL" \
  --tenant "$TENANT" --subject "$SUBJECT" \
  --model-sha256 "$MODEL_SHA256" --tokenizer-sha256 "$TOKEN_SHA256" \
  --limit 32
```

`--doctor` verifies complete SQLite-to-file custody, plus the global audit
chain. `--verify-only` validates exported observations without modifying the
outbox. `--after-sequence N` reads bounded committed delivery metadata for a
local consumer. `--follow-ticks N` runs a finite, operator-owned poll loop.

This is **not** an exactly-once external delivery guarantee. Exactly-once
here means one immutable local file identity per committed event; an API or
external sink needs its own independent idempotency contract and credentials.

## Failure matrix

| Fault | Expected behavior |
|---|---|
| Crash before file fsync | Partial file remains held for operator review |
| Crash after fsync, before SQL ack | Exact byte replay, no duplicate event file |
| Crash after ack | Source and saved receipt remain verifiable |
| Published file deleted or mutated | Doctor and next publisher pass hold |
| SQLite row deleted or source hash mutated | Doctor holds, no synthetic repair |
| Spool owner / model changes | Refuse adoption and leave prior state untouched |
| New upstream event field | Refuse export until source schema reviewed |
| Unknown outbox kind | Leave unacked and private; never export |
| Concurrent publishers | Kernel-held spool lock serializes file writes |
| Unapproved or missing real GGUF | Not qualified by this metadata subsystem |

No self-asserted package completeness, model performance, native generation,
clean-machine installation, customer hardware, or final-head CI success is
implied by these local tests.
