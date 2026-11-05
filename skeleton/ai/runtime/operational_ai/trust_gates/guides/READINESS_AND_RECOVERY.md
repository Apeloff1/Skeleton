# Operator-grade AI readiness and recovery sequence

## Before model activation
Validate that the actual installation receipt binds the exact model and
tokenizer digest to source-bound bytes. Inspect actual installed file
descriptors and model licenses. Run the GGUF-native E2E on the intended machine;
the contract suite does not substitute for this.

## Before local serving
Pin a model epoch. Admit each request against current deadline, quota and
runtime capacity, then serialize the native backend's actual output and usage.
Use the canonical SQLite conversation transaction and journal as the real
authoritative commit fence, not the process-local helper tables.

## On failure or cancellation
Reject replay of a request until the durable commit state is known.
Refuse cancellation acknowledgment while native execution remains active.
Release only local reservations whose commit did not occur. Do not assume
unknown telemetry means healthy operation.

## On recovery
Follow the six ordered inventory, key, journal, chat, approval and restore
phases; each phase needs independently verified evidence. Never use a
simulated fixture as an operator-signed proof. Reload exact pinned model
bytes, verify SQLite replay semantics and compare the final SHA.

## On promotion
All ten named security and CI checks must show success at the final commit,
with no queued, skipped, failed, cancelled or superseded statuses. Reviewer
approval, real model E2E, installation and model rights are independent holds.
A metadata validator cannot query GitHub or prove external truth by itself.
