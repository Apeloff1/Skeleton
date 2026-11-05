# Expedition save journal and conflict-safe recovery

An expedition save journal is a bounded append-only sequence of complete
canonical expedition reports. Every revision must strictly extend the prior
input action history and preserve all three gameplay event prefixes. Every
report is independently replay-verified; the journal also has an authenticated-
structure-style hash chain, but **no publisher signature** is claimed.

Use \`expedition-journal-init\` with \`--expedition report.json\` to create a
journal. \`expedition-journal-append\` requires the existing journal, a newer
verified report and the exact \`--expected-expedition-journal-digest\` CAS
lease. \`expedition-journal-at\` reconstructs a historical revision using
\`--revision-index\`. \`expedition-journal-fork\` creates an independent
historical branch without overwriting the original journal.

\`expedition-journal-compare\` reports identical, left-ahead, right-ahead or
diverged ancestry. \`expedition-journal-fast-forward\` accepts **only** a
strict right-ahead descendant and an exact left-journal CAS lease. Divergent
branches are not silently combined, and terminal games cannot be extended.
All comparisons are portable and replay-verifiable.

This is deterministic offline custody. Durability of writing files to disk,
cross-process locks, trusted identity, external backup, device performance
and release qualification are separate responsibilities.
