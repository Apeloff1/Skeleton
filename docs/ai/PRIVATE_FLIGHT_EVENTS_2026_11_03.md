# Private resumable AI flight events — transport v2

This module exposes **verified state transitions**, not uncommitted model tokens.
A native request is still written to the exact-identity SQLite flight ledger;
its worker runs independently and records progress and terminal state.

## Client contract

1. Operator provisions a private 0600 bearer using the existing flight-server CLI.
2. Run the existing `transport.flight.serve` and submit work through its authenticated
   `POST /v2/operations` interface.
3. Read `GET /v2/jobs/<job_id>/events?limit=32&wait_ms=1000` with `Authorization: Bearer`.
4. Interpret the finite `text/event-stream` response as a list of `transition` events
   followed by one `checkpoint` event, then close the connection.
5. Resume by appending the exact `cursor=` value returned by the checkpoint;
   the cursor is HMAC-bound to principal, job, ordinal and event SHA-256.
6. Reconnect after service restart; the cursor remains valid while the private
   bearer and exact authoritative job ledger are unchanged.
7. Once the checkpoint says terminal, query `job` and `replay` to retrieve the
   separately authorized committed result. Event responses never include prompt
   text, model output, source passages or private worker paths.

Use `python -m skeleton.ai.runtime.operational_ai.transport.flight.event_stream.cli`
with `--bearer-file`, `--job`, `--port`, `--rounds` and optional `--cursor` to read
bounded observations. The watch command has a finite default and never submits
work, runs a model, calls tools, or approves recovery.

## Safety and recovery

- Each snapshot is read transactionally and verifies the **entire** bounded
  per-job event chain, canonical event hashes, linked outbox records, legal
  state transitions and principal ownership.
- Corrupt or missing event/outbox data yields HTTP 503. No fabricated empty
  progress or optimistic terminal state is returned.
- A cursor from another job, principal or bearer returns HTTP 400; a valid MAC
  referring to a changed chain returns HTTP 409.
- At most 32 events (policy ceiling 64) and two seconds of bounded long-poll
  are allowed per request. SQLite transactions are not held during waiting.
- Host, bearer, browser-Origin, request framing and concurrency refusal come
  from the existing strict loopback HTTP server. No public browser access.
- This is an observation protocol, **not** a new completion path. Native
  completion remains one authoritative atomic durable commit.

## Model-gateway regression discovered during integration

The capacity-model package `model/admission/` unintentionally shadowed the
older `model/admission.py` import used by `ModelGateway`. This source
restores `InferenceAdmission` in the package interface and explicitly tests
simultaneous import of the per-worker gate and the new global capacity broker.

The gateway also now checks native response SHA against actual text and counts
invalid receipts, identity changes, context overruns and quota failures toward
its circuit breaker. Without that check, malformed native receipts could
escape model-failure accounting.

## Qualification

The focused suites use real SQLite, actual HTTP loopback, independent process
fences from the existing runtime, and an intentionally **fixture-backed** model.
They do **not** prove an approved GGUF checkpoint, human-level model quality,
GPU capacity or clean-device installation. All existing mandatory exact-head
CI, security, rights and release holds still apply.
