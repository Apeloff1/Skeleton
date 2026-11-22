# Zaibatsu retained event custody

The historical Python Outbox declared restart durability but kept only a deque.
The historical Fabric verified a trimmed hot tail against genesis, could expose
mutable payloads, and lost all chain state on restart. The repaired local SQLite
journal commits admission, monotonic fabric sequence, event bytes and chain head
in one transaction. Generic deliveries compact after confirmation; fabric
delivery confirmations retain the original source records. Capacity limits
include both pending and retained data. The system refuses further admission at
capacity instead of dropping history.

Configure ZAIBATSU_OUTBOX_PATH to a private persistent local directory. The
default is backend/data/zaibatsu/events.sqlite3. Do not share on a network
filesystem. Each sink must upsert/deduplicate on the reserved _outbox_id.
Confirmation is at-least-once: an external write may succeed just before a crash;
the same stable ID will be delivered again after lease expiry. Keep independent
backup and external chain-head anchors; unkeyed hashes cannot prove resistance
against a malicious actor able to rewrite the entire database and checkpoint.
The new v2 event format binds ID and every event field. Rust/C# parity and
migration from historically mirrored external events are explicitly separate
qualification tasks. No automatic historical import or deletion is attempted.

Exact focused qualification:
    cd backend && python -m pytest -q tests/test_zaibatsu_retained_journal.py tests/test_zaibatsu_island_integration.py tests/test_durable_outbox.py
