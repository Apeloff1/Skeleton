# Jeeves competitive compute — phase VIII

This increment targets the parts of the existing native model that do
unnecessary repeated CPU work. It does not replace the local model owner,
tokenizer format, checkpoint schema, sampler, source identity or durable
conversation authority. No network, remote provider, additional package or
hardware dependency is added.

## 1. Ordered indexed BPE

The existing character BPE encoder used one full sweep of the surviving
stream for every trained rule. For 256–131072 input codepoints and at
least 16 merge rules, maintain a doubly linked logical token sequence
and an inverted occurrence index of only those adjacent pairs referenced
by model rules. Consume the original edges of each rule in sorted
left-to-right order; remove overlapping occurrences and touch only
adjacencies affected by a merge. Endpoint versions prevent a newly
created occurrence from being consumed during its own merge wave, even
for unusual restored rule sequences or duplicate pairs. The actual
trained merge order remains authoritative: no greedy substitution,
alternate vocabulary, normalization change or approximate tokenizer.

Scratch is linear in admitted characters; large inputs and short/few-rule
inputs use the original scan. The indexed path is most attractive when
many rules are irrelevant to the particular prompt. Worst-case work
includes sorting each matching occurrence wave, and no latency claim is
made without measurement.

## 2. Sparse sampling after exact top-k

The existing dense softmax and stable top-k probability selection remain
the same. When k is less than one eighth of the vocabulary, retain only
positive selected probabilities, traverse the support in original token
index order, preserve min-p and top-p renormalization order, stable ties,
and one RNG draw. The expensive subsequent nucleus sort becomes a sort of
at most k entries, rather than sorting the whole zero-padded vocabulary.
This does not eliminate dense output projection or dense initial softmax.
Seeded parity, masks, underflow, ties and boundary thresholds are tested.

## 3. Rotary phase table

For default-base reference CPU vectors of width 2–512, share immutable
geometry-only sin/cos phase tables across Q/K, layers and repeated
positions. Cache at most 128 entries; custom bases, other widths and
noninteger positions use original math. Input values are never stored.
Each position uses the original operation order, not a recurrent
approximation. The Cortex source and governed runtime mirror must stay
byte-identical.

## 4. Explicit same-owner shared-prefix batches

NativeLLMRuntime.generate_batch(..., reuse_shared_prefix=True,
prefix_budget_bytes=...) is opt-in. All requests are previously admitted
and uniquely identified, and must belong to one trusted caller scope.
Use lexicographic token-prefix ordering to cluster related prompts,
then emit results in original request order. One real CPU KV bank is
trimmed to the previous admitted prompt (never generated continuations);
reuse a compatible exact longest common prefix for the next request.
Recompute the final needed logit, preserve request seeds and independent
sampling, and use the canonical generation stream and complete terminal
receipt. Reject shifted origins and stale model revisions. Retention is
bounded by the smaller of the requested byte budget and one-quarter of
the runtime KV ceiling using the existing conservative Python object
estimate. No prefix is retained after the batch returns or crosses a call.
Unsupported, uncached, accelerator/routed or disabled requests retain
the old execution path; cancellation discards unreturned work.
Physical execution order can differ under explicit opt-in. This is
sequential shared-prefill work reduction, not fused GPU batching or
concurrent decode. It is not enabled by default for unrelated callers.

## 5. Rolling sampling penalties and incremental stop search

The real decoder maintains exact recent-token counts via a bounded deque
and Counter whenever repetition/presence/frequency penalties are active.
Eviction and insertion are constant-time bookkeeping; penalties still
apply to the current dense model logits and per-token identity checks.
No change to repetition-window membership, penalty arithmetic, suppression
or min-token policy.

For the exact canonical word tokenizer without BPE, the incremental stop
matcher retains at most max-marker-length minus one characters from the
previous output, and tracks the earliest absolute stop index even before
minimum output tokens. It handles a later completed longer marker that
starts earlier than a previously observed marker. On a hit, verify the
index against the actual full canonical decode before publishing text.
No-match completion still uses the canonical decode. BPE and custom
tokenizers keep the full-decode path because unknown tokens or custom
decoding can change prior rendering. Buffering semantics and terminal
receipts are retained. Tokenizer output-budget checks still apply.

## Prior exact-head evidence and repairs

At head 3af95edb150b84e9548749a3759421b4498945d3, Jeeves source job
133055748212 executed 247 focused tests successfully. Its later legacy
contract step passed 377 and failed one because a grounding observer had
the old no-keyword engine signature. The observer now forwards and
asserts the actual trusted session/tenant scope without weakening its
untrusted-source assertions. Browser/native SQLite recovery, App
Foundation E2E, Backend Quality, exact AI-tree identity, Sealed Context
Guard, repository hygiene, dependency review and source-bound installer
custody passed on that prior revision.

Draft19 custody job 133055717543 failed collection due to a nonexistent
Studio archive test identifier. Replace it with the existing parameterized
invalid-custody and source-tamper tests. No security/custody checks
removed. Re-pin exact Cortex Git object from the committed source tree
after synchronized BPE/attention edits.

The new focused suite exercises actual native batch transformer-step
reduction and replay-receipt parity, budget denial, sliding windows,
independent invocations, random and adversarial BPE rule migration,
seeded sparse sampler equivalence, rotary math, rolling penalties,
Unicode/cross-token stop detection and actual full-decode call counts.
All new claims remain source implementation until exact-head CI executes.
No production hardware benchmarks, physical memory, GPU/GGUF fused
batching, production weight improvement, merge or release are certified.
Rollback has no persistent data or format migration.
