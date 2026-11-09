"""Approved persistence measurements and strict local lookup."""
from importlib import import_module
ALLOWED=frozenset(('audit_parity', 'receipt_replay_rate', 'sqlite_conflicts', 'outbox_backlog_ratio', 'db_file_growth', 'checkpoint_age', 'orphan_fraction', 'transaction_failure_ratio', 'restoration_integrity', 'wal_bytes_ratio', 'immutable_file_coverage', 'revision_gap'))
def measure(name,observations):
    if name not in ALLOWED:raise ValueError('unknown measurement contract')
    module=import_module('skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.persistence.'+name)
    return module.measure(observations)
