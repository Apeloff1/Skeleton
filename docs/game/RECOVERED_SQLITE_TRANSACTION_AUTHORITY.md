# Recovered SQLite save and journal transaction integrity

The pre-existing GF-B SQLite adapter updated a process-local checkpoint
window before a SQL transaction began, used that stale window to prune
other writers' committed rows, and removed only the newest in-memory
entry on failure. Replay append similarly updated memory before SQL and
used INSERT OR IGNORE, allowing a second connection to report a conflicting
event as accepted. These problems directly affect the new recovered
movement/quest save workflows.

Both canonical and staged mirror files now use SQLite as committed
authority. Checkpoint monotonic admission and retention run in one
BEGIN IMMEDIATE transaction; no local sequence or history mutation is
published before commit. Journal idempotence checks the committed row
inside a transaction; conflicting or corrupted events are rejected,
not silently ignored. Reads consult current SQL rows, checkpoint row
identities are bound to the SQL keys, corruption is rejected during
restore, and journal heads stream the canonical digest-list encoding.
Retained history, event sizes and streaming entry counts are bounded.

Parallel participants must use independent database connections and a
cooperatively managed local database. This does not claim hostile database
tamper resistance, cryptographic authentication, power-loss durability,
unbounded stream retention, or device qualification. New trigger-based
tests cover insertion/pruning failure, cross-connection conflicts,
corruption after open and exact canonical/mirror bytes; execution of the
tests has not yet been observed.
