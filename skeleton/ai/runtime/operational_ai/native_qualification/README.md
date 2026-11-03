# Native AI qualification plane — real inference, no mock substitution

This package is an executable, source-pinned **real-model acceptance lane** for
Skeleton's existing offline `NativeChatEngine` / `NativeLLMRuntime` /
`OfflineAIService`. It adds no competing model implementation, hosted
fallback, game builder, synthetic weight bytes, or fabricated generation.

The operator-provided checkpoint is already validated by the canonical
`transport.cli.build_service` path. The evaluator only accepts an actual
`OfflineAIService` backed by `NativeBackend` and an enabled per-session
process fence. Each original case creates a real durable conversation and
calls the native generation path with a deterministic seed. The receipt is
checked for session, request, model/tokenizer identity, revision and output
non-emptiness. Raw prompts and model replies are not placed in the report.

## Reproducible entry points

```sh
python -m skeleton.ai.runtime.operational_ai.native_qualification.cli --inventory
python -m unittest discover -s skeleton/testing -p 'test_native_qualification*.py' -v
python -m compileall -q skeleton/ai/runtime/operational_ai/native_qualification
```

For real inference, provision an **approved and SHA-256-verified native
checkpoint** and a private state directory (all three SQLite stores share it).
Then use this form, replacing arguments with actual operator-controlled values:

```sh
python -m skeleton.ai.runtime.operational_ai.native_qualification.cli \
  --run-native \
  --checkpoint /trusted/models/native.json \
  --sha256 ACTUAL_SHA256_64_LOWERCASE_HEX \
  --license operator_reviewed \
  --database /private/ai/chat.sqlite3 \
  --memory-db /private/ai/memory.sqlite3 \
  --journal-db /private/ai/audit.sqlite3 \
  --output-directory /private/ai/qualification_reports
```

The tool never downloads weights, cannot fabricate model output, has no
network tool, and cannot promote or deploy a model. Its source corpus is
**480 original cases / 20 domains / 24 cases per domain**. The `--domain`
option creates an intentionally incomplete development report; it cannot
qualify the full corpus.

## Evidence interpretation

A result is a genuine pass only when a real native response satisfies all
explicit checks. Failed calls, malformed JSON, missing citations, omitted
continuity, leaked synthetic secrets, fabricated facts, wrong source identity
and incomplete evidence remain failures. All case files are original and
versioned. The complete-case proof compares every exact case digest with the
shipped corpus; a substitute or partial inventory cannot count as complete.

The report contains hashed principal, session and request references, usage,
latency, output digest, per-check results and an immutable corpus digest,
**not the model text or prompts**. Optional private SQLite report ledger HMACs
protect against offline modification, deletion and same-run conflicting
receipts. Its MAC is not a signature or proof of licensing.

A 95% threshold is a policy floor, **not** a frontier-quality claim. A score
above that floor still does not establish real device performance, model
rights, privacy in the wild, security against unknown prompts, or product
readiness. Even a perfect score leaves `release_certified`,
`merge_certified`, `ci_qualified` and `hardware_qualified` false
until independent exact-head gates and real-device checks have completed.
