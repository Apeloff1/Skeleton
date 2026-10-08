# Native LLM runtime core

This runtime is the executable FLGB-02 bridge from governed text input to the
repository-owned causal transformer and back to generated text. It does not
create a second model implementation. The numerical engine remains
`skeleton/cortex/transformer.py`; this plane makes that engine safe to serve.

## Implemented on this branch

- bounded text/chunk ingestion with exact source digests and stable tokenizer identity;
- deterministic context windows, token batching and canonical token-sequence serialization;
- explicit prompt IDs versus newly generated IDs (no prefix/output ambiguity);
- incremental KV decode and uncached reference decode through the same transformer;
- temperature/top-k/top-p/seed/stop-token decoding with fail-closed validation;
- deterministic streaming events and replay receipts;
- portable model/checkpoint identity, shape validation and tamper detection;
- explicit re-admission after model-weight mutation;
- logical model/KV memory admission and batch token budgets;
- CPU-default placement with bounded optional accelerator fallback policy;
- checkpoint JSON round-trip including attached BPE state;
- architecture and health snapshots for embeddings, position handling, heads, layers and FFN shape.

## Authority and completion status

This is implementation evidence only. FLGB-02 stays `implemented-pending-verification`
until exact-head CI, dependency closure and independent verification succeed. No
masterplan completion signature is asserted by file existence or by this document.

## Focused validation

```bash
python -m unittest tests.flgb.test_flgb_02_tokenization_pipeline -v
python -m unittest tests.flgb.test_flgb_02_native_llm_runtime -v
python -m unittest discover -s tests/flgb -p 'test_flgb_02_*.py' -v
```

## Canonical scheduler recovery and deployment pins

`restore_admission_scheduler(snapshot)` rejects type coercions, unknown or
missing fields, contradictory active/KV state, forward-dated sequences,
duplicate enqueue sequences, invalid token budgets, over-capacity entries,
noncanonical collection order and mismatched telemetry capacity. It does not
acquire external authority. Callers restoring persisted state should pass
`expected_policy`, `expected_limits`, `minimum_sequence` and
`expected_digest` read from **independent trusted** deployment metadata.
Sequence floors mitigate accidental stale-state rollback; a checksum alone does
not prevent replay or certify the checkpoint's publisher.

Retained KV identities are reserved while their cache entries exist. A new
request cannot silently reuse such an identity: explicitly evict/release
retained state before reusing it. Active records must retain identical KV
byte reservations and pinned flags, while queued requests never own KV entries.

`restore_admission_scheduler` currently caps retained KV checkpoint entries
at 65,536; productions expecting larger pools must set and validate an
architecture-governed bounded storage policy before changing that limit.

Focused suites:

```bash
python -m unittest tests.flgb.test_admission_checkpoint -v
python -m unittest tests.flgb.test_admission_checkpoint_strict -v
python -m unittest tests.flgb.test_runtime_admission_scheduler -v
```

Retries also enforce the bounded admission queue before modifying active
request state. A full queue makes `retry` fail atomically, keeping the
running request and resident KV available for explicit cancel, completion,
or a later retry after space becomes available. Constructor limits are typed.

## Deterministic admission state-machine stress tests

`tests/flgb/test_admission_checkpoint_state_machine.py` executes seeded,
interleaved submit, admit, retry, complete, cancel and KV pin transitions.
Every state is restored with trusted policy/limits/sequence pins; the test
requires exact checkpoint parity, bounded KV, queue and active occupancy,
atomic failed submissions/retries and equal traces for identical seeds.
The retained KV eviction scenarios exercise both pinned and unpinned state.
This is finite model-based randomized regression, **not** a claim of exhaustive
formal verification or production workload qualification.

```bash
python -m unittest tests.flgb.test_admission_checkpoint_state_machine -v
```

### Explicit retained KV release

`RuntimeAdmissionScheduler.release_retained_kv(request_id)` releases only an
inactive completed request's retained KV entry. It never releases active
decode state or queued ownership, and rejects missing identities without
mutating scheduler state. Pinned retained KV may be explicitly freed by a
authorized operator/control caller; callers must enforce tenant/request
authority upstream. The release increments the scheduler sequence and is
covered by checkpoint recovery tests, allowing deliberate later request-ID
reuse without evicting unrelated caches.
