# Jeeves causal efficiency — phase X

## Exact last-query execution

For the standard reference CPU graph with a context of at least sixteen
tokens, uncached next-token inference takes an explicitly causal path.
Earlier transformer blocks still produce every hidden position. They
stream one token through the existing reference step kernel while keeping
only that block's keys and values and its output hidden rows. Intermediate
queries, normalization caches, attention matrices, residuals and FFN
activations are no longer retained across the whole block.

At the final block, preceding positions contribute their normalized
keys and values only. Compute the query and output/FFN transformations
for the last position. This removes N-1 query and output projections and
N-1 final-layer feed-forward passes for an N-token input. All prior keys
and values remain included in the original causal softmax. No approximate
attention, token eviction or learned-position change. Training, routed
graphs, custom instance hooks, accelerator graphs and short contexts
retain the existing full path. Tests compare exact logits and count real
matrix projection invocations on deterministic graphs. This optimization
is most relevant to uncached and fallback inference; ordinary cached
prefill already avoids repeated vocabulary projection.

Reference CPU matvec calls now poll between blocks of at most 128 output
rows when a cancellation callback is supplied. Each row retains its
original dot-product accumulation. Interrupting an incomplete decode
still invalidates the partial bank. This bounds row-group work, not a
physical cancellation time or the work inside one extremely wide row.

## Tokenizer admission and hot-path identity

Freeze the already immutable vocabulary manifest digest at admission;
do not build and encode the same token/ID inventory again for every
integrity check and checkpoint operation. Validate the live vocabulary,
embedding count, specials, and actual token-to-ID lookup on each check.
A mutated lookup table formerly could change encoding without changing
the snapshot vocabulary. Reject inconsistent or noninteger IDs, added
aliases, removed entries or vocabulary/special drift.

Compare builtin BPE snapshot bytes against the admitted canonical digest
without a JSON decode/re-encode roundtrip. No-BPE checks avoid even that
serialization. Custom snapshot providers keep normalized legacy
semantics. Tokenizer checkpoint schema and digest construction are
unchanged. Checks remain linear in vocabulary size, without full
manifest-sized JSON allocation on each token.

## Lossless packed private KV banks

The live conversation owner pool, native session retention and explicit
same-owner batch path compact successfully completed eligible CPU banks
into standard-library arrays of native double-precision values. A
64-bit float keeps its original value, including signed zero; this is NOT
quantization. Compact at idle handoff with a minimum payload budget and
exact row/shape/finiteness validation. Convert one row at a time to avoid
holding an entire second graph. Keep only conversions that reduce the
estimated Python object footprint. Read packed rows directly during
native attention; newly appended rows may be lists until the next
handoff. Preserve scopes, epochs, compatibility, aggregate retention
limits, source-model checks, existing spill representation and reset
behavior. The public external cache API and accelerator storage are
not converted by default.

Use Python object accounting that counts the actual array allocation and
does not charge boxed float objects for elements stored in a contiguous
buffer. Physical RSS and driver memory remain unmeasured. Reduced idle
retention footprint may allow more reusable prefixes at the same ceiling;
reading a packed row can introduce boxing overhead. No measured latency
gain is claimed.

## Qualification and inherited blockers

The phase IX head d100bc7eddcd00925d0639d2a0fe391641232afb passed App
Foundation E2E, exact AI-tree identity, Sealed Context Guard, hygiene,
dependency review, secret scanning and installer/source custody. It
failed bounded Forge archive qualification in two jobs: one obsolete
node-forge install-time mutation conflicting with the exact reviewed
source pin, and one eight-mode public API contract not wired through
the inherited three-mode generation path. The latter remains an
explicit integration hold; no test is weakened or suppressed.

Recover the no-write RSA install verification and regression from
review-only PR 5421 at 7f34e85f12f80d5ae7f9692e049b2cd0dc4031b1.
No dependency, digest, DER anchor or hostile signature probe changes.
The pristine installed package still must actually pass the reviewer
pin. If it does not, retain independent security review. Phase IX
focused and browser jobs were cancelled on supersession, and cannot
qualify the newer tree.

Enroll new actual graph parity, final-layer work count, cached
interruption, stable tokenizer identity and lookup drift, packed bank
payload/accounting, warm/cold logits and scoped reuse regressions.
Synchronize governed Cortex source/mirror bytes and exact object pin.
All existing merge, device, independent evaluation and release holds
remain; no physical memory benchmark, production model improvement,
GPU/GGUF kernel fusion or deployment is certified.
