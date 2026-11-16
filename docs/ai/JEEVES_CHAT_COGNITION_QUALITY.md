# Jeeves Chat: conversational cognition and matched quality qualification

## Delivered
The authenticated loopback chat has an explicit **Conversation intelligence & recall** panel. It reads the selected current transcript and up to three explicitly selected additional same-model conversations, with one SQLite snapshot. It scans at most 512 messages per session, ranks exact user excerpts with weighted lexical overlap, reports excluded history, suppresses near duplicates, and labels explicit preference, rejection, correction, unfinished-work, temporal and verification cues. Assistant output is never treated as user memory. Exact message and excerpt hashes, offsets, session revision, model and tokenizer identity accompany the preview.

The panel lets the operator copy individual excerpts or select a suggested output budget. It does not change the draft, system instructions, persistent memory, model weights, source permissions or chat request identity. The original context preview and generation admission still apply. Cross-session selection is opt-in and is limited to currently loaded conversation summaries. A copied passage is not a new trusted source or a future freshness guarantee.

The independent evaluator scores exact answers, literal inclusion/exclusion, word limits and closed JSON keys; human rubric findings are explicitly pending. Complete capture identity, answer hashes, case/turn/protocol/model identity and unique receipt digests are mandatory. It compares only matching suites and protocols. This initial corpus is 30 hand-authored cases across dialogue, instruction following, memory, structured output, personalization, reasoning, writing, multilingual communication, grounding, temporal understanding and calibration.

## Execute after source qualification
```sh
python -m unittest skeleton.testing.test_jeeves_chat_cognition_quality
python -m compileall -q skeleton/app/jeeves_chat_cognition.py skeleton/app/jeeves_chat_quality.py skeleton/app/jeeves_chat_quality_cases.py skeleton/app/jeeves_chat_benchmark.py
```

Start a dedicated authenticated local Jeeves browser service with a qualified installed model. The benchmark creates new durable conversations and retains them. Never run against a personal workspace without consent. Obtain the exact model digest from the local status surface. Use a private output directory and the actual owner-only token file.

```sh
python -m skeleton.app.jeeves_chat_benchmark run --port PORT --token-file PRIVATE_TOKEN_PATH --model-digest EXACT_SHA256 --output private-report.json --output-tokens 512 --execute
python -m skeleton.app.jeeves_chat_benchmark compare baseline.json candidate.json --output comparison.json
```

The runner uses only 127.0.0.1, does not follow redirects or proxy settings, checks the returned execution identity and durable session readback, and never retries uncertain requests. The wall-clock budget is checked between calls; a request may overrun due to socket behavior/server activity. A failed or interrupted benchmark leaves the created conversations available for inspection and does not publish a complete evaluation. Reports contain actual answer text and should remain private. A matching digest is not an independently signed receipt. Model/tokenizer change, missing/incompatible answers or insufficient context holds the run.

## Outstanding
- Actual semantic embeddings, cross-session long-term memory lifecycle (including deletion, revision conflict and expiration), semantic compression and automatic contextual injection with exact-token custody are not delivered by this heuristic layer.
- True independent semantic judging, blind human review, expanded multilingual corpus, actual long-context and thousand-turn experiments, benchmark datasets/rights, and matched runs on competitor weights are still required.
- Native image/audio/video understanding, voice interaction, agentic tool calls, full chat streaming/artifacts, underlying model training and deployment are independent capabilities; none are implied by this change.
- Exact-head CI, browser E2E, canonical parity, local real-model execution, and platform/security qualification are required before promotion. No merge or release authorization.
