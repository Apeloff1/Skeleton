# Shell Evidence, Replay, and Retention

## Purpose

Execution evidence should answer what logical command ran, under which
correlation, how many attempts occurred, whether it succeeded, whether it timed
out, whether it hit output limit, how much output existed, how long it ran, what
control state surrounded it, and whether evidence was modified.

Evidence should answer those questions without becoming a second secret store.

## Evidence types

The shell plane has several evidence forms.

ExecutionReceipt records per-attempt canonical metadata.

ReceiptChain records a tamper-evident ordered chain.

AuditEvent records executor lifecycle events.

ShellEvent records control-plane dispatch events.

ShellSpan records bounded tracing data.

ShellFailureRecord records low-cardinality failure classification.

ShellSnapshot records aggregate control-plane state.

ShellIncident records operator incident context.

WorkerJournal records hash-chained worker lifecycle events.

These forms have different retention and sensitivity needs.

## Receipt contents

Receipt stores no stdout or stderr bytes.

It stores byte counts.

Metadata should remain bounded and secret-minimized.

Receipt IDs are random UUID-style hex by default.

Receipt chain links by SHA-256.

## Receipt integrity

For each chained receipt the hash covers prior hash, sequence, and receipt
dictionary.

Verification checks expected sequence, expected prior hash, and recomputed
current hash.

Any mismatch invalidates chain verification.

## Root hash

ReceiptChain root hash identifies the current chain head.

Store root hash in snapshots, incidents, deployment records, change records, and
shutdown handoff.

Root hash alone does not prove who produced it.

## HMAC attestation

HMACAttestor adds symmetric keyed integrity.

The key is caller-provided and never serialized in the attestation object.

Attestation contains key ID, algorithm, payload digest, and HMAC-SHA256
signature.

Use external secret management for HMAC keys.

Rotate keys by key ID.

Retain old verification keys for required audit period.

## Public-key provenance

HMAC is not public-key nonrepudiation.

If external verification is required, add an asymmetric attestation adapter.

Do not replace receipt chaining when adding asymmetric signatures.

## Replay

EvidenceReplay verifies evidence only.

It never invokes ShellRunner or ShellExecutor.

Replay can validate receipt chain and per-receipt HMAC attestations.

Missing attestation and invalid attestation remain distinguishable.

## Result index

ReceiptIndex improves metadata query performance.

It is not source of truth.

If index and chain disagree, chain is authoritative.

Index eviction does not alter chain.

## Execution history

ExecutionHistory provides bounded operational history.

It can summarize total, success, failure, timeout, output-limit, and per-command
counts.

History may evict old receipts by capacity.

For durable audit use an external append-only sink.

## Audit events

Audit events can contain correlation, command, attempt, fingerprint, argv
digest, environment-key digest, session ID, receipt ID, return code, status
flags, byte counts, duration, and hook failure names.

Audit events should not contain raw argv by default.

Audit events should not contain environment values.

Audit events should not contain stdout or stderr.

## Control events

ShellEvents tracks control-plane transitions.

It is a bounded ring.

Useful events include admitted, started, completed, and error.

A terminal event without a start is an invariant problem.

A start without terminal may indicate in-flight work or interrupted control
flow.

## Trace spans

Trace attributes should be low cardinality.

Good attributes are logical command, plan step class, retry attempt bucket, and
service phase.

Risky attributes are raw argv, file contents, output, user text, secret IDs, and
arbitrary environment values.

## Failure ledger

Failure detail should classify rather than reproduce.

Good detail includes DeadlineExceeded, capability denied, workspace escape, and
return code rejected.

Bad detail includes entire exception with stdout, full environment, credential
bearing command line, or response bodies containing tokens.

## Output classification

Output content is handled separately.

Classes are public, internal, sensitive, and secret.

Classification can be command-defined, pattern-based, or outer-policy supplied.

Pattern classification is defense in depth, not guaranteed secret discovery.

## Default retention

Public output can retain bounded bytes and digest for moderate period.

Internal output should retain smaller bounded bytes and digest for shorter
period.

Sensitive output should retain no bytes and optionally a digest.

Secret output should retain no bytes and use the shortest metadata retention.

## OutputRetentionStore

Store enforces item count, aggregate retained bytes, and expiry.

It stores only bytes already allowed by OutputRetentionPolicy.

Replacing an item accounts for prior retained bytes.

Expired items are removed lazily or by explicit prune.

## Digest sensitivity

SHA-256 output digest can itself be sensitive when underlying output has low
entropy.

Treat output digests as internal evidence.

Do not automatically expose them publicly.

## Execution cache

ExecutionCache stores fingerprint, command, return code, status flags, byte
counts, output digests, timing bounds, and hit count.

It does not store output bytes.

The cache does not prove command purity.

Only explicitly safe deterministic operations should use it.

## Cache key design

A strong future cache key should include command fingerprint, policy revision or
fingerprint, command contract version, relevant workspace digest, and relevant
fixed environment version.

Do not reuse result solely by logical command name.

## Snapshots

ShellSnapshot includes status, diagnostics, cancellations, concurrency, budgets,
and receipt root.

Snapshot digest identifies captured payload.

Snapshots are internal by default.

## Incident evidence

Incident evidence should point to other evidence.

Preferred fields are receipt ID, receipt root, snapshot digest, rollout ID,
policy revision, change ID, correlation ID, and failure kind.

Avoid copying raw child output, secret environment values, credentials, or user
documents.

## Change evidence

ChangeControl stores payload digest.

The source change can remain in source control or review system.

This reduces duplication.

## Policy evidence

PolicyStore records fingerprint per revision.

Fingerprint includes paths and key names.

Treat policy exports as internal.

## Plan evidence

ExecutionPlan fingerprint is deterministic.

Plan shape includes argv and cwd.

If argv contains secrets, plan material is sensitive.

Preferred design keeps secrets out of argv.

Use approved environment or secret injection channels.

## Worker evidence

WorkerJournal is separate from ReceiptChain.

Worker events describe ownership and lifecycle.

Receipts describe execution attempts.

Both can be correlated by IDs in higher-level adapters.

## Evidence export

An audit export should preserve receipt IDs, sequence, chain hashes, schema
version, export timestamp, source root or snapshot, and redaction state.

Require audit-export authority where applicable.

Sign exports when needed.

## Retention tiers

Hot tier holds recent events and traces for fast query and short retention.

Warm tier holds receipt metadata, incidents, and policy or plan revisions.

Cold tier holds signed audit exports and compliance archives.

Skeleton in-memory stores are hot and warm primitives, not archival systems.

## Deletion

Deleting retained output bytes does not require deleting receipts because
receipts contain counts and digests, not output bytes.

Deleting a receipt from a chain invalidates later hashes.

For privacy requirements needing deletion, design external evidence with
appropriate redaction or cryptographic erasure.

Do not mutate an existing chain and continue treating it valid.

## Capacity planning

Estimate memory for receipt count, event count, trace count, failure count,
output retained bytes, incident evidence, and plan or policy histories.

All local stores should have explicit bounds.

## Incident capture

When an execution incident occurs:

1. record failure classification
2. ensure receipt exists if execution occurred
3. capture shell snapshot
4. verify receipt chain
5. open incident
6. reference correlation, receipt, and snapshot
7. preserve rollout or change IDs
8. classify output before retaining bytes
9. export evidence if required
10. do not rerun command merely to reproduce evidence

## Shutdown evidence

Before controlled shutdown capture status, diagnostics, reconciliation, receipt
root, worker snapshot, open incidents, policy revision, and relevant plan
versions.

After restart compare expected continuity.

## Receipt verification failure

If receipt verification fails, stop trusting the chain after corruption, open a
critical incident, capture raw current state, do not rewrite hashes, identify
mutation source, restore from trusted external evidence if available, and start
a new chain only with explicit incident boundary.

## Attestation failure

If HMAC verification fails, verify key ID and key version, verify canonical
payload representation, treat evidence as untrusted until resolved, and never
silently re-sign a modified receipt.

## Reconciliation evidence

Reconciler findings are derived evidence.

Store them with snapshot, change, and incident context when operationally
relevant.

A clean reconciliation does not prove child output was safe.

## Testing requirements

Retain tests for receipt tamper, chain tamper, HMAC payload tamper, HMAC
signature tamper, missing attestation, invalid attestation, cache expiry, cache
eviction, output byte non-retention, sensitive and secret retention defaults,
retention capacity, incident evidence bounds, event sink isolation, trace stale
finish, duplicate receipt rejection, and history eviction.

## Operator checklist

Before exporting evidence verify receipt chain, identify receipt root, identify
attestation key version, apply output classification, remove secrets, record
snapshot digest, record schema version, approve destination, and know retention
duration.

## Principle

Evidence should be rich enough to prove what happened while remaining too poor
to become an accidental copy of everything the child process knew.
