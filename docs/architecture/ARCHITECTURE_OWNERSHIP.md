# Architecture Ownership

<!-- machine-git-blob: machine/architecture_ownership.json@429282f802fb49d83a8885f7dd913aaf576fd37b -->

Machine authority: `machine/architecture_ownership.json`

This control implements the P2 masterplan owner-lookup and AI-root ownership-graph gaps in VOL-002 and VOL-051.

Repository paths have two related identities:

- **physical owner/zone** comes from the longest canonical-root and zone-root prefix in `machine/architecture.json`;
- **semantic owner/zone** normally equals the physical identity, but a destination inside an explicit `migration:staged-mirror` AI-tree mapping inherits the source semantic owner/zone until cutover.

That distinction is required for governed compatibility/research mirrors such as `backend/... -> skeleton/ai/compat|research/legacy/...` and native acceleration mirrors under `skeleton/ai/runtime/native`. Their physical storage location does not silently transfer production authority.

Cross-root or cross-zone aliases are allowed only when the exact AI-tree mapping has a staged-mirror tag, a `cutover:*` disposition, and a non-empty source disposition. Undeclared transfers still fail closed. Unknown roots never inherit ambient authority.
