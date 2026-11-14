# Replay-verified player combat campaign route search

`python -m skeleton combat-campaign-solve demo` searches the original
two-encounter campaign using **actual canonical human turns**, not a parallel
simulation. `solve --source-json '<json>'` searches authored content;
`solve --session-json '<json>'` resumes from a verified checkpoint. These
inputs are mutually exclusive. `verify --report-json '<json>'` recomputes
the exact bounded search, victory, and portable bundle. An optional
`--expected-source-digest` fences the author's expected source revision.

State, depth, choice and frontier limits are enforced separately. Results
are `solved`, `inconclusive` with explicit budget reasons, or
`no_victory_in_explored_graph` (not an unwinnability certificate).
A winning witness includes legal player actions, the canonical terminal
session, and a round-tripped portable save. Receipt hashes detect accidental
or adversarial changes but are **not signatures or source authorization**.

Focused validation after remote publication:
`python -m unittest skeleton.testing.test_combat_campaign_solver -v`.
Tests cover earned victories, restart, export/import, budget exhaustion,
tampering with recomputed hashes, source lease, invalid saves and CLI.
Do not claim consumer or release readiness without exact-head CI.
