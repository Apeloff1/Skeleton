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
disk free-space reserve before new writes. On POSIX, it also performs a bounded
descriptor-relative inventory under the cooperative publication lock before
each new object and checkpoint. The default 4 GiB per-spool byte quota can be
set with `max_spool_bytes` (1 byte to 1 TiB); it accounts for orphan temp files
and counts hardlinked temporary/final names only once. Untrusted directory
entries, unreadable metadata or exhausted scan bounds deny publication.
This is a cooperative local filesystem budget, not a guarantee against
malicious same-UID writers or external processes allocating disk concurrently.
Windows path fallback is not qualified for the POSIX descriptor-relative
quota; platform and filesystem quotas remain necessary. Reserve checks cannot
replace filesystem quotas or handle concurrent writers consuming disk after
the probe.
POSIX publication also bounds cooperative lock contention by both monotonic
elapsed time and an independent maximum retry count. Invalid or regressing
monotonic clock observations fail closed; a frozen clock cannot spin forever
or authorize an unchecked write. The lock is not a defense against hostile
same-UID filesystem writers.
The root and its parents must be operator-controlled; on POSIX the root must
not be group/world writable. Symlink reads use O_NOFOLLOW where supported.
Windows cannot claim POSIX-equivalent symlink race protection.

Focused tests:

```bash
python -m unittest tests.flgb.test_long_context_spool -v
```

Full model/OS qualification, source provenance, device memory safety and
release readiness remain separate mandatory gates.

## Bounded token materialization

`LongContextSpool.next_window` now caps each in-memory token tuple independently of the serialized context size. The default maximum is 4,096 tokens per window; a trusted application can select a lower limit or explicitly configure up to 65,536. Oversized requests fail before loading token content or advancing immutable checkpoints. This is a host-memory allocation bound, not a device-memory or GPU qualification. Production execution must still independently enforce actual CPU/GPU/thermal budgets and acknowledge progress only after completed work.

## Payload-free bounded capacity observation

The `capacity` command reports a POSIX descriptor-relative, cross-process-lock
serialized inventory and current disk headroom without disclosing token IDs,
checkpoint digests, source names or tenant content:

```bash
python -m skeleton.ai.model_runtime.long_context_cli --root ./private-token-spool --tokenizer-digest DIGEST capacity --request-bytes 1048576
```

The `observed_publishable_bytes` value is the minimum of quota headroom
and free volume bytes after the configured disk reserve. `state=hold` is a
conservative observation; `state=observed_available` is **not** a lease,
permission grant, GPU qualification, or guarantee of a future write. Publication
still independently revalidates quota and free space under the same lock.
Both observation and actual POSIX publication reject negative, boolean,
nonintegral, oversized or unavailable filesystem block counters *before*
computing disk headroom; an apparently positive product of invalid negative
counters never grants disk admission. A failed telemetry probe leaves no new
immutable object or checkpoint receipt.
Unreadable, untrusted, oversized inventory or unknown volume telemetry fails
closed. The POSIX scanner is cooperative, not a defense against malicious
same-UID filesystem mutation. The Windows fallback is deliberately unsupported
for this diagnostic until descriptor-relative custody is independently qualified.
