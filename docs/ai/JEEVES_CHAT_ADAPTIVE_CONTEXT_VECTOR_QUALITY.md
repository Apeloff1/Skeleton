# Jeeves Chat — adaptive context, local vector recall and response quality

This review-only candidate extends #5470 at exact parent 32502bd2b85f06f874425bfeac13e2533987ee95. It changes the existing authenticated offline browser workspace and its canonical local chat service, not the underlying model weights.

## Adaptive context

Open **Adaptive conversation context** in a selected local conversation. Explicitly choose eligible memory kinds, note count (0–4), byte budget, response approach and optional continuation/tag or learned-vector retrieval. Plan, inspect the exact resulting message, then apply it or generate with that exact reviewed draft. A second server plan must match the first digest before applying. The ordinary chat route, request idempotency, token admission, runtime lease, transcript and execution receipt remain authoritative.

- Candidate generation retrieves approved notes by lexical/subword ranking, bounded recent user-authored anchors for short continuations, and optionally one hop through matching user-approved tags or installed word vectors.
- Possible conflicts are flagged by bounded same-label, overlap and negation rules. All detected group members are withheld. This is a conservative heuristic within the retrieved pool, not exhaustive semantic contradiction detection.
- Relevance, diversity, duplicate suppression and exact note identity drive packing. Optional profiles and notes cannot cause additional history omission relative to the original draft's model-window estimate. Native token estimates use the existing tokenizer; GGUF estimates remain conservative bytes and need final runtime admission.
- The reviewed context becomes part of the actual **visible user message**, with the original question first. No hidden prompt injection, privileged tool grant, automatic memory write, or independent evidence claim. Deleting a note later does not remove prior chat copies. Plan snapshots may become stale after the final preview; normal generation independently checks the current context. The local grounding mode remains separate so augmented drafts do not silently change document retrieval scope.
- Response approaches: neutral, direct, analytical, technical, creative, tutor, critical review. These are user-selected instructions, not trained capability improvements.

## Optional learned vector recall

The static word-vector encoder requires an independently obtained, appropriately licensed local pretrained vector asset. Nothing is bundled or downloaded. It accepts a bounded UTF-8 JSONL file: header with schema skeleton.jeeves.word-vector-asset.v1, model_name, dimensions (4–512), and vocabulary count (1–250,000), followed by ascending unique canonical word/vector rows. Each row is a two-element JSON array. Import verifies the exact raw bytes against an operator-supplied SHA-256 and commits the bank atomically into the canonical model/tokenizer-scoped private SQLite store. The asset cap is 256 MiB.

A text conversion command is available for plain whitespace-separated learned word vectors (optional vocabulary/dimension header). Its temporary SQLite ordering stage avoids holding the entire vocabulary as Python objects. The source hash is checked over all raw bytes; conversion publishes a new output only. The optional lossy flag explicitly skips unsupported punctuation/nonword tokens and keeps the first admitted normalized collision. It does not accept malformed dimensions, NaN or zero vectors. A converted inventory is not an original vendor artifact or an independently verified license.

    python -m skeleton.app.jeeves_memory_vector_cli convert --source WORDS_TXT --source-sha256 SOURCE_SHA --destination WORDS_JSONL --name ENCODER_NAME --dimensions 300 --header --max-rows 50000 --approve
    python -m skeleton.app.jeeves_memory_vector_cli install --database PRIVATE_DB --model-digest MODEL_SHA --tokenizer-digest TOKENIZER_SHA --asset WORDS_JSONL --asset-sha256 CONVERTED_SHA --approve
    python -m skeleton.app.jeeves_memory_vector_cli status --database PRIVATE_DB --model-digest MODEL_SHA --tokenizer-digest TOKENIZER_SHA
    python -m skeleton.app.jeeves_memory_vector_cli refresh --database PRIVATE_DB --model-digest MODEL_SHA --tokenizer-digest TOKENIZER_SHA --asset-sha256 CONVERTED_SHA --approve

Repeat refresh with its next_cursor or use the workspace **Optional learned-vector recall** controls. Replacement requires --expected-prior, and removal requires the current exact asset SHA and approval. No HTTP filesystem path installation is provided. The database and derived index contain private memory content; perform large imports while the local service is idle and ensure disk headroom. Existing private SQLite/WAL custody applies; encrypted storage and physical erasure are not asserted.

Actual dense retrieval pools locally installed learned word vectors, records word coverage, indexes note revisions, and computes exact cosine over candidates. It uses a deterministic six-band, eight-bit multiprobe angular locality-sensitive hashing index when the active eligible vector population exceeds 4,096. The approximate stage is disclosed; it does not prove exhaustive nearest-neighbor recall. Missing/stale index entries are excluded, bounded refresh is explicit, selected result sources and vectors are rechecked, and candidate/coverage truncation is visible. Digests are integrity checks, not independent signatures; a malicious actor who controls the entire private database can rewrite it. This is static word-vector retrieval, not a pretrained transformer sentence encoder, and no physical 100k-memory benchmark or model quality victory has been measured.

## Answer quality and refinement

**Review answer** on a saved assistant turn binds a rating to the exact question, raw answer, visible audited publication, model and tokenizer. Feedback supports explicit helpful/mixed/needs-improvement ratings, flags and an optional note, versioned edit/remove, cascade on source deletion and a bounded recent summary. Historical/forked turns lacking runtime receipts are kept distinct. Rating does not change model weights, trust scores, automatic behavior or source authority.

Deterministic hints detect explicit numeric English word caps, strict JSON-only parse failures, unclosed code fences, repeated long lines and possible action-claim cues. They can be wrong and are not semantic evaluation. For the latest saved turn, prepare a critique, verification or refinement follow-up, optionally using reviewed flags. The actual inference remains the normal user-sent model turn and requires full-history preflight. Older answers can first be branched through existing controls. No hidden model calls or automatically certified critique.

## Evaluation at scale

The original 30 hand-authored cases remain. The generated inventory adds 16 distinct task families with seeded parameter variations and a requested 8–1,000-turn dialogue whose final question requires an immutable code from its first turn. Up to 25,000 cases may be described per complete inventory (including baseline and long case if selected). Generated variants are not 25,000 independently authored or semantically distinct tasks. Existing default local context/activation and actual device capacity can prevent long-dialogue execution.

    python -m skeleton.app.jeeves_chat_benchmark inventory --no-baseline --generated-count 25000 --seed 42 --output private-inventory.json
    python -m skeleton.app.jeeves_chat_benchmark inventory --no-baseline --long-turns 1000 --seed 42 --output private-long-inventory.json

Actual benchmark execution still needs the previously documented qualified, authenticated local service; use the existing run command with --generated-start, --generated-count, --seed, --no-baseline and/or --long-turns. Live runs are limited to 4,000 captured turns and 16 MiB of answer text per shard, in addition to the existing deadline/report bounds. Use disjoint case ranges. Aggregate only complete matched raw-answer capture shards:

    python -m skeleton.app.jeeves_chat_benchmark aggregate --no-baseline --generated-count 200 --seed 42 --input private-shard-a.json --input private-shard-b.json --output private-aggregate.json
    python -m skeleton.app.jeeves_chat_benchmark compare baseline-report.json candidate-report.json --output private-comparison.json

Aggregation recomputes each shard's scoring from captured text, checks exact expected case/turn coverage, identical model/tokenizer/protocol identity, disjoint shards and unique execution receipt digests. Cross-model comparison still requires matched suites/protocols. Raw answer captures and summaries are private. No independent attestation of external receipts, human rubric judgment or real-model comparative score is supplied by this source work.

## Validation and holds

After the full source candidate is assembled:

    python -m unittest skeleton.testing.test_jeeves_chat_cognition_quality skeleton.testing.test_jeeves_approved_memory skeleton.testing.test_jeeves_chat_memory_workspace skeleton.testing.test_jeeves_adaptive_context_vectors skeleton.testing.test_jeeves_turn_feedback_scenarios skeleton.testing.test_jeeves_chat_eval_aggregate
    python -m compileall -q skeleton/app/jeeves_adaptive_context.py skeleton/app/jeeves_memory_vectors.py skeleton/app/jeeves_memory_vector_cli.py skeleton/app/jeeves_turn_feedback.py skeleton/app/jeeves_chat_eval_scenarios.py skeleton/app/jeeves_chat_eval_aggregate.py skeleton/app/jeeves_chat_benchmark.py skeleton/app/offline_http.py skeleton/app/offline_web.py skeleton/app/local_ai.py

Focused tests use synthetic vectors and receipts only. Require actual browser E2E, no-network verification, exact-head CI, canonical parity/security, installed word-vector asset qualification, measured large index recall/latency, native/GGUF device execution and independently evaluated competitor results. No tests are claimed executed by this authoring session. Keep no-merge/no-release holds. Learned neural sentence embeddings, hidden context custody without changing user messages, semantic compression, automatic multi-pass inference, native voice/vision/audio/video and genuine model training are distinct outstanding capabilities.
