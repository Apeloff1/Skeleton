# Jeeves local advantage — phase VII

The competitive target is not a claimed frontier benchmark. It is useful
private inference on existing hardware, with verifiable local evidence,
less repeated work, and recoverable conversation custody. All changes
extend existing owners rather than creating a parallel service.

## Live exact native CPU prefill

The earlier opt-in NativeConversationSession cache now has a complementary
host-scoped retention pool in the canonical prepared local model adapter.
The desktop creates an opaque per-host owner and uses its actual session
identity; the HTTP application supplies one opaque process-local owner
across its short-lived durable session adapters. Ordinary unregistered
backend calls remain cold. The native canonical generation stream, token
admission, device/weight identity checks, stream audit and terminal
execution receipt remain mandatory.

A lease transfers exclusive ownership of an idle CPU bank. Compare exact
token IDs; keep their longest common prefix rather than requiring the old
entire prompt to be present. For a shortened prefix, clear last-position
logits and recompute from the first changed token. Never reuse shifted
origins, routed graphs, resident accelerator tensors, an incompatible
revision/profile, or another host/conversation. A candidate bank is
published only after successful terminal audit and visible-output parsing.
The durable adapter invalidates its cache after a failed SQLite commit.
Deletion and host shutdown revoke owned banks; epoch fences prevent a
revoked or superseded lease from publishing. No cache storage on disk.

Default idle ceiling: lower of 8 MiB Python object estimate and one-quarter
of the runtime maximum KV budget; at most eight registered scopes, also
subject to the native runtime aggregate idle cap. LRU eviction and a
120-second expiry checked on pool operations bound retained state. Expiry
is lazy, not a timed erasure guarantee. Clearing releases objects, not
secure RAM wiping. Actual resident physical RAM, latency and GPU/GGUF
prefill acceleration are not established. Counters represent lease and
retention observations, not verified speedup.

## Optimized local grounding and context

Sparse lexical queries now collect only matching verified rows with a
bounded 2 MiB estimated scratch budget and at most 2048 candidates while
the entire model-scoped source and chunk custody pass is running. Compute
the original score once corpus term frequencies are known. When the
scratch limit is exceeded, release it and fall back to the existing exact
same-SQLite-snapshot replay. Both paths retain original score, tie order,
document scope, source coordinates and SHA identities. No mutable external
index, stale cross-transaction trust, or full-corpus materialization.
Integrity verification remains linear in corpus size.

Desktop, actual HTTP turns and HTTP read-only previews choose source
excerpt sizes from a finite ladder (220, 160, 120, 80, 48 characters).
The full candidate is preferred when it fits all history. Otherwise use
the largest feasible evidence width that preserves the most history.
Every selected source remains represented. A compact excerpt must belong
to the original broad source span and preserve observed query terms,
numeric literals and explicit qualifiers, including negation. This is
a conservative lexical check, not a semantic entailment guarantee.
If sources cannot fit under the requested output/context and strict
history policy, refuse rather than silently remove evidence, invent a
summary, shrink requested output, or degrade to ungrounded generation.
Saved evidence retains the existing schema, exact excerpt byte SHA,
character offsets and source revision. Actual generation rechecks the
same durable history; preview remains non-authoritative.

GGUF's existing conservative UTF-8 byte-based history estimate now
selects the longest whole-turn suffix with one reverse accumulation
rather than repeatedly serializing the full history. Preserve historical
front-pair trimming even for odd ephemeral histories. Native uses its
exact tokenizer and observes tokenizer and total-token ceilings; capacity
errors can trigger permitted trimming but identity errors cannot. Fix
the preview separator to match actual newlines sent during inference.
No change to actual GGUF runtime/tokenizer authority.

## Assurance

Prior exact head b38540e74f369397dad326ff99f85891a647d335:
- Source job 133052915175: 232 passed, one failing fault-injection callback
  signature. Repair the callback to accept the actual optimizer arguments.
- Exact tree job 133052913712: full parity passed, integration object
  pins failed. Read the committed Git tree recursively for all 28
  selected source identities and reconcile five stale pins.
- Backend job 133052931447: explicit live-service boundary passed; one
  repository machine taxonomy test failed on skeleton/admission.
  Assign the repository writer lease to the existing repository control
  plane without relaxing the classification test.
- The prior workspace browser and App Foundation E2E jobs passed.
  Neither qualifies this head.

Enroll actual private LCP reuse/cold parity, owner isolation, lease
revocation, expiry, cancellation, bounded memory, HTTP durable reuse,
source compaction anchors and preview, exact suffix estimation, sparse/
dense parity and corruption tests. Preserve all architecture, safety,
device, independent evaluation, CI and release holds. No production
benchmark, production weight update, independent physical qualification
or merge/release authorization is claimed. Rollback has no new persistent
schema or checkpoint format migration.
