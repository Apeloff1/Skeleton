# Operational AI — restart-safe native work and evidence

The work-order queue provides a real durable SQLite ledger for offline AI
requests. It exists alongside the canonical GGUF+ExecutionSpine, not in
place of it. Its input identity binds tenant, subject, model and tokenizer
digests, session, request, exact prompt SHA256, seed, temperature and output
cap. Prompt plaintext and bearer secrets are never written to this queue.

## Fail-closed native sequence

1. Configure an explicit tenant token ceiling in a private directory.
2. Submit an immutable work order. A reused ID with different input fails.
3. Reserve tokens and claim with a 256-bit random lease and revision CAS in
   a SQLite BEGIN IMMEDIATE transaction.
4. Write a durable **dispatch-unknown** marker before calling the actual
   supervised native model. Never treat an exception as evidence of no effect.
5. Only read-only authoritative ExecutionSpine.replay may establish a commit.
   Check source model/tokenizer, text SHA, prompt/response token accounting.
6. Charge the actual committed tokens and free the unused reservation
   atomically with job revision, full event bytes/hash chain and outbox event.
7. On missing replay, keep the job fenced. No speculative regeneration or
   automatic token refund.
8. An undispatched lease can be cancelled only by its original lease token
   and operator approval. A dispatch-unknown job cannot be cancelled as
   though the native process never ran.

## Adversarial acceptance

Focused tests cover source collisions, tenant/subject scope, model epoch
drift, SQLite WAL recovery, cross-thread admission, budget CAS, failed
native execution, absent canonical replay, mutated journal bytes, event
hashes, quota discrepancies, bad token counts, outbox isolation, and
fail-closed operator cancellation.

Use: `python scripts/check_ai_work_orders.py`

These tests use actual private SQLite files plus a **contract-only FakeWorker**.
They do not assert a real GGUF model was loaded, a Windows/WSL2 laptop was
installed, any external model rights were approved, or final-head CI passed.

## Required independent release qualification

Real approved GGUF installed bytes, source rights, device pressure/latency,
native cancellation and restart, independent review and all ten exact-head
security and CI workflows remain unresolved until directly observed.
