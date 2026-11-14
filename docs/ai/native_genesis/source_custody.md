# Source custody, permissions and original-only status

Canonical corpus: `native_candidate/examples/v1`.
The 576 examples comprise 24 domains with 24 original synthetic examples
each. Every example records a stable source ID, domain, group, prompt,
completion, original license, scope and provenance. It is never admitted
just because a JSON parser accepts it.

Source admission verifies schema equality, bounded UTF-8, no duplicate keys,
no source ID collisions, no normalized duplicate prompts, and the complete
24-by-24 source inventory. An independently implemented answer oracle
re-derives the completion for every example from the source prompt.

Corpus partitions are deterministic and group-disjoint: 432 train, 72
validation, and 72 holdout. Training and tokenizer construction must use
ONLY train, even when validation and holdout contain more recent task forms
or vocabulary missing from training.

Training rights are bound to `skeleton_original` and the explicit
`offline_native_candidate_training` scope. No redistributable or licensed
third-party weights are created by the source pipeline. The approved source
scope does not grant product release approval.

Changes to examples alter source hashes, tokenizer vocabulary hashes,
generation manifests and, typically, actual model identities. Re-run all
source assertions, the exact-head security gates and independent quality
evaluation when source content changes.
