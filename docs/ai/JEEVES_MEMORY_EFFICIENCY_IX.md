# Jeeves memory efficiency — phase IX

The native model has an advantage when the same hardware must also run
the game builder, reference archive and local automation. This pass
reduces avoidable model graph retention and checkpoint loading work while
preserving canonical identity checks at their existing boundaries.

## Detached model snapshot lifetime

Native runtime admission still captures and validates the actual model
snapshot, binds its digest and calculates its exact existing logical
size. Previously the runtime kept the entire snapshot (including all
matrix rows) in an unused private member. Release the detached graph as
soon as admission completes. Refresh likewise retains the new digest and
size, not an additional full graph. No cached hash replaces current
model verification. Checkpoint publication still builds a separate
detached snapshot; no read-only-memory or zero-copy claim is made.

## Bounded canonical numeric encoding

The existing checkpoint serializer hashes identical canonical UTF-8
JSON using sorted keys and the original JSON options. Numeric blocks of
at most 1024 elements use the standard C JSON encoder; recursively emit
container delimiters, field names and bounded blocks. This avoids a
Python iterator fragment per scalar in complete numeric rows. Retain
standard encoding for mixed/custom objects, handle circular references
and reject nonfinite numbers. Exact canonical digests, byte counts and
bounded size checks remain required.

Calculate complete checkpoint envelope size from the canonical digest-free
body length and exact fixed SHA field overhead. This eliminates a second
full envelope hash performed only for sizing and another pass during
restore. Enforce the complete envelope ceiling at checkpoint creation.
Existing JSON checkpoint format, identity and size semantics are unchanged
except for stricter rejection of complete envelopes that exceed the limit.

## Direct reference restore

Authenticate all checkpoint bytes, verify tensor shapes and declared
model digest, and validate source limits/device policy before allocating
an executable graph. Check logical model footprint and context limit
before constructing it. For complete canonical non-MoD CPU graphs,
initialize only the actual detached matrices, vectors and required
metadata, not a random placeholder transformer and a second set of
placeholder layer tensors. Preserve tied embeddings, normalization,
activation and position mode. Reject inconsistent first-layer aliases or
tied matrices before allocation. Legacy/incomplete or routed formats
continue through the historical loader. Re-admit the executable graph
and compare its actual canonical identity to the pinned model digest;
reject a restore that silently canonicalizes different weight bytes.
The existing tokenizer checkpoint and architecture checks remain.

Direct construction reduces avoidable allocations and RNG work; it has
not been independently measured for production-sized model loading,
physical memory, device mapping or acceleration.

## Source qualification and historical integration

Prior exact head 66c9e7104d34eab3ea744ff8b695fab9506eee2f:
266 focused regressions, 378 legacy source tests and two additional
tests passed. Browser/native SQLite recovery, App Foundation E2E,
backend quality, AI-tree exact identity, sealed context, dependency
and Draft19 archive custody passed. The larger source job then failed
frontend typecheck. Repository hygiene found one trailing whitespace
line; workflow security detected credential-shaped synthetic database
fixtures. Repair the formatting and explicitly label the short mock
database passwords as nonproduction example fixtures without weakening
the scanner or exposing actual credentials.

Remove duplicate declarations and recover the source-backed genre
control and Jeeves diagnostic catalog declarations from historical
candidate 29e52352511905c3ee40eb0552ec9638154632af. Reconnect its
read-only diagnostic catalog to the existing evaluation module.
Restore saved-design handling, preserve historical optional metadata
and current playtest/source export choices, and explicitly hold
full historical Galaxy and mini-game choices that this branch's
archetype-only generation endpoint does not yet implement. Do not
silently convert those settings into a different project. Full
Galaxy/mini-game backend integration remains a separate gap.

New tests cover large and mixed canonical payloads, size thresholds,
invalid values/cycles, exact SHA parity, direct restore without random
constructors, actual generation receipt parity (including tied/rotary
graphs), resource/policy rejection before construction, no mutable
row aliasing, contradictory duplicate fields and restored graph
identity. Existing quarantine, CI, native hardware, installer and
release requirements stay in force. No merge, release, production
benchmark, or independent physical memory qualification is claimed.
