# Recovered Jeeves frontier campaign archive

The candidate P0/P1/P2/P3 composition, session replay, campaign ledger,
export, archive, retention, snapshot, history, compaction and history
receipt owners now run as one bounded source-replay workflow. Source
orders are retained as immutable SQLite events under a scope and a
caller-pinned predecessor. Appends use BEGIN IMMEDIATE and refuse
stale heads, duplicate manifests and corrupt prior source. A read-only
audit reconstructs all canonical owners and verifies every event hash,
then projects retention and compaction without deleting source history.

Limits: 128 events per scope, 8192 candidate steps per scope, 512 steps
per order, 16 MiB retained source per scope and cooperative 256 MiB
database page limit. SQLite WAL growth, filesystem custody, hostile
parents, physical capacity and crash/power-loss qualification require
separate evidence. The archive does not load weights or authenticate
supplied mesh evidence. Independent chain head custody is mandatory.

Four canonical/mirror owners also close session digest substitution,
nested receipt mismatch, duplicate campaign session identity and mutable
caller-owned session references while preserving historical valid hash
formats. All source validation and original qualification suites remain
pending actual execution. No native/release authority is granted.
