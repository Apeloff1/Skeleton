"""Approved persistence measurements and strict local lookup."""
ALLOWED=frozenset(('audit_parity', 'receipt_replay_rate', 'sqlite_conflicts', 'outbox_backlog_ratio', 'db_file_growth', 'checkpoint_age', 'orphan_fraction', 'transaction_failure_ratio', 'restoration_integrity', 'wal_bytes_ratio', 'immutable_file_coverage', 'revision_gap'))
def measure(name,observations):
    if type(name) is not str or name not in ALLOWED:
        raise ValueError('unknown measurement contract')
    if name == "audit_parity":
        from . import audit_parity as module
    elif name == "receipt_replay_rate":
        from . import receipt_replay_rate as module
    elif name == "sqlite_conflicts":
        from . import sqlite_conflicts as module
    elif name == "outbox_backlog_ratio":
        from . import outbox_backlog_ratio as module
    elif name == "db_file_growth":
        from . import db_file_growth as module
    elif name == "checkpoint_age":
        from . import checkpoint_age as module
    elif name == "orphan_fraction":
        from . import orphan_fraction as module
    elif name == "transaction_failure_ratio":
        from . import transaction_failure_ratio as module
    elif name == "restoration_integrity":
        from . import restoration_integrity as module
    elif name == "wal_bytes_ratio":
        from . import wal_bytes_ratio as module
    elif name == "immutable_file_coverage":
        from . import immutable_file_coverage as module
    elif name == "revision_gap":
        from . import revision_gap as module
    else:
        raise ValueError('unknown measurement contract')
    return module.measure(observations)
