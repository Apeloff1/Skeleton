# Laptop-first operational AI: live risk register

These are explicit release blockers, not completed features merely because
source code or a fixture exists.

## Native inference and source custody

The source-bound install receipt must be independently approved and checked
against the *actual* on-disk GGUF bytes before model activation. Tokenizer
identity is model-bound in the GGUF path and is not an independently signed
third-party tokenizer attestation. The native backend must actually load and
generate a response on the intended target laptop; expected token and context
usage must be observed rather than estimated. Incomplete model provenance,
unreviewed rights or unknown hardware telemetry must hold activation.

## Data, authorization and tools

The local HTTP boundary permits only loopback IP, strong bearer credential,
exact Host, no browser Origin, bounded bodies, no Transfer-Encoding ambiguity
and an independent concurrency cap. Model output is plain text, never an
authority to execute a tool, install a package, access another tenant's
memory or upgrade a checkpoint. Canonical SQLite state, not process-local
helper registries, owns durable inference idempotency and memory consent.
The API has no write-memory or dangerous-tool operation.

## Failure and recovery

A cancellation signal does not prove the active native model was forcibly
stopped. A blocked inference after durable reservation must be recovered using
the existing authoritative repair and outbox custody protocol. A repeated
request must replay the exact prior committed receipt without generating a
different answer. The database must pass independent SQLite integrity, hash
chain and principal binding checks after cold restart. Source-only schema
test success does not establish those runtime behaviors.

## Release and portability

Windows 11 + WSL2 install, Docker/Compose integration, clean machine and
real memory/disk pressure remain unqualified without device evidence.
Backend readiness, tokenizers, model licensing, temperature quality, GPU
pressure, true streaming and independent adversarial review are held. Exact
head Merge Readiness, Backend Quality, App E2E, Workflow Input Security,
Sealed Context Guard, Artifact Policy, Malware, Repository Hygiene,
Secret Scanning and Dependency Review all need success, not skipped or
cancelled. Draft stacking must be reconciled before any mainline merge.

## Evidence to collect

Run the focused source-contract suite only after the complete batch exists.
Then run explicit real-source install doctor, live GGUF first turn, durable
replay/restart and target laptop power/resource tests. Preserve exact SHA,
model hash, source license approval and timestamps in the resulting review
record. Never claim 99.9% from structural file counts alone.
