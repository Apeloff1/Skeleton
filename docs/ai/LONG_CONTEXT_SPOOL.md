# Offline long-context token custody (v1)

`LongContextSpool` persists native tokenizer output and resumable progress as
immutable, content-addressed files under an operator-owned private directory.
The canonical tokenizer identity, source-text digest, token sequence digest and
parent checkpoint are bound into every receipt. The returned checkpoint digest
is the resume token. A second process can load it and continue without
re-tokenizing a large authored prompt.

This is **token custody**, not a serialized transformer KV cache, model
checkpoint, encryption system, or a substitute for the guarded model-serving
admission. The hash detects modification but does not authenticate a publisher.
Do not store private prompts on a shared or untrusted filesystem. Operators
control the spool directory and are responsible for backup, secure deletion and
durable external retention of the latest acknowledged checkpoint digest.

## Python integration

```python
from skeleton.ai.model_runtime import LongContextSpool

sequence = native_tokenizer.encode_sequence(original_story_prompt)
spool = LongContextSpool("./private-token-spool")
cursor = spool.stage(sequence)
window = spool.next_window(
    cursor, expected_tokenizer_digest=native_tokenizer.digest, max_tokens=512
)
# Only acknowledge tokens actually consumed by the governed runtime.
cursor = spool.advance(
    cursor, expected_tokenizer_digest=native_tokenizer.digest,
    consumed_tokens=len(window.token_ids)
)
```

`NativeTokenizer.stage_text(text, spool)` combines source-bound tokenization
and staging; it refuses an invalid spool and tokenizer drift.

## Offline CLI

Prepare a canonical token sequence with
`serialize_token_sequence(native_tokenizer.encode_sequence(text))`.
Then run:

```bash
python -m skeleton.ai.model_runtime.long_context_cli --root ./private-token-spool --tokenizer-digest DIGEST stage --sequence-file ./sequence.json
python -m skeleton.ai.model_runtime.long_context_cli --root ./private-token-spool --tokenizer-digest DIGEST inspect --checkpoint CHECKPOINT
python -m skeleton.ai.model_runtime.long_context_cli --root ./private-token-spool --tokenizer-digest DIGEST window --checkpoint CHECKPOINT --max-tokens 512
python -m skeleton.ai.model_runtime.long_context_cli --root ./private-token-spool --tokenizer-digest DIGEST advance --checkpoint CHECKPOINT --consumed-tokens 512
```

The CLI emits machine-readable JSON and does not execute models. Stage and
advance use temporary files, fsync and atomic hard-link publication. Existing
content-addressed objects are never overwritten. A crash may leave a hidden
temporary file but cannot publish a partial checkpoint. A retried identical
operation produces the same digest. No mutable `latest` pointer is created:
two concurrent consumers may advance independently without lost updates.
The caller must retain its last acknowledged digest and must not infer that
a crash after a model operation proves the operation completed.

A bounded read verifies file type, canonical encoding, object digest,
tokenizer identity, sequence identity, cursor bounds and direct ancestry.
The store enforces a configurable per-sequence byte ceiling and a conservative
disk free-space reserve before new writes. Reserve checks cannot replace
filesystem quotas or handle concurrent writers consuming disk after the probe.
The root and its parents must be operator-controlled; on POSIX the root must
not be group/world writable. Symlink reads use O_NOFOLLOW where supported.
Windows cannot claim POSIX-equivalent symlink race protection.

Focused tests:

```bash
python -m unittest tests.flgb.test_long_context_spool -v
```

Full model/OS qualification, source provenance, device memory safety and
release readiness remain separate mandatory gates.
