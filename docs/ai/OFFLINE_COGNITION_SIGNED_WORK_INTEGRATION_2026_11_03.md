# Signed grounded offline AI — laptop-first integration and adversarial acceptance

The existing SupervisedAI and ExecutionSpine remain authoritative for all
native GGUF execution and durable session replay. WorkOrderStore and
SignedIngress retain SQLite and HMAC custody; no new service, provider,
policy owner or permanent state store is introduced.

## Operator-to-native sequence

1. Independently verify the approved original source bytes and the current
   model/tokenizer receipt. Bind each source to tenant+subject and SHA-256.
2. Prepare a principal-scoped EvidenceIndex, using bounded per-scope BM25.
   Foreign tenant documents cannot influence BM25 document frequency, length
   averages or ranking scores for the selected principal.
3. Call grounded_work.prepare with the actual question, source policy, byte
   limits and optional externally measured model-SHA-bound embedding vector.
   There is no synthetic dense fallback. Source spans and quoted text are
   verified against original bytes, then serialized as JSON data rather than
   system policy. No model generation occurs during preparation.
4. Call bind_work_order with a trusted caller-owned job ID, existing durable
   session ID and idempotency request ID. This binds prompt SHA, model,
   tokenizer, tenant, subject, sampling parameters and output budget.
5. Obtain an external signed HMAC approval token from the existing operator
   authority; retrieved documents and model output may not sign themselves.
6. submit_signed revalidates the exact original source, composed prompt and
   immutable request before SignedIngress atomically consumes the HMAC nonce
   and creates the queued job. No native effects occur during admission.
7. execute_signed_once verifies a matching signed admissions-table row,
   canonical SQLite chain and real backend identity before calling the
   pre-existing WorkOrderExecutor exactly once.
8. Native execution reserves the durable tenant token budget and writes
   dispatch-unknown BEFORE model inference. A lost reply cannot be treated
   as a safe retry. Only canonical read-only replay can reconcile it.
9. Output SHA, actual charged tokens and source provenance are returned.
   A valid source quote is not proof of semantic entailment, device quality,
   license rights, comparative model superiority or release readiness.

### Failure contracts

- Foreign principal or model with identical weights: reject before replay
  or inference, even when source IDs and request IDs are known.
- Stale source, modified quote or swapped SHA: reject before HMAC admission.
- Denied or expired operator grant: deny; no substitute permission.
- Direct WorkOrderStore.submit without the signed admissions record: deny
  at the native bridge, even if a queued job exists.
- Ambiguous effect after native dispatch: no automatic retry or quota refund;
  retain the held source work order and reconcile only from canonical SQLite.
- Best-effort diagnostics saturation after committed generation: return
  authoritative native receipt; count diagnostics drop rather than converting
  the output into an ambiguous failed request.
- Unknown or stale GitHub check: hold merge/release. Source tests never
  substitute for exact final-head checked security, rights or laptop evidence.

## Source-controlled regression inventory

- 64 capability families, 20 typed operation adapters per family.
- 2,560 policy casebooks (128 permitted, 2,432 intended adversarial denials).
- 256 additional original-source adversarial integration cases:
  128 isolation perturbations, 112 untrusted-source JSON quotation cases
  and 16 expected refusals for embedded NUL source data.
- 28 focused grounded-work tests, including fake-worker tests of true SQLite
  HMAC nonce consumption, source integrity, replay, quota and idempotency
  contracts. FakeWorker is an explicitly labeled test double, not GGUF.

## Reproducible tests

    python scripts/check_offline_cognition.py --focused
    python scripts/check_offline_cognition.py --full

The full source test is inserted into the existing Merge Readiness Unit
job. No additional workflow was created and the admission cap is untouched.
Draft PRs deliberately do not run this unit gate; release certification,
native real-model E2E, target Windows/WSL2 cold install and independent model
rights remain separate fail-closed qualification holds.

## L00–L13 handoff

L00–L02: one canonical native/SQLite/provider authority, typed data and
versioned receipts. L03–L05: authenticated signed admission, bounded byte
packing, immutable original source identity and one native dispatch.
L06–L07: principal isolation, foreign corpus poisoning, prompt injection,
tampered SHA and crash uncertainty are refused; no implicit retries.
L08–L09: finite document/token/byte/latency/slot budgets with private
diagnostics and provenance receipts. L10: source-controlled positive,
negative, HMAC, SQLite and adversarial tests. L11–L12: existing state
doctor, real restart and rollback owned by the canonical laptop operator.
L13: enterprise superiority and final release remain unqualified without
current exact-head comparator/device/security evidence.
