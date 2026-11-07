"""Approved persistence measurements and strict local lookup."""
from importlib import import_module
ALLOWED=frozenset(('audit_parity', 'receipt_replay_rate', 'sqlite_conflicts', 'outbox_backlog_ratio', 'db_file_growth', 'checkpoint_age', 'orphan_fraction', 'transaction_failure_ratio', 'restoration_integrity', 'wal_bytes_ratio', 'immutable_file_coverage', 'revision_gap'))
_LOADERS = {
    "audit_parity": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.persistence.audit_parity"),
    "receipt_replay_rate": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.persistence.receipt_replay_rate"),
    "sqlite_conflicts": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.persistence.sqlite_conflicts"),
    "outbox_backlog_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.persistence.outbox_backlog_ratio"),
    "db_file_growth": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.persistence.db_file_growth"),
    "checkpoint_age": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.persistence.checkpoint_age"),
    "orphan_fraction": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.persistence.orphan_fraction"),
    "transaction_failure_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.persistence.transaction_failure_ratio"),
    "restoration_integrity": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.persistence.restoration_integrity"),
    "wal_bytes_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.persistence.wal_bytes_ratio"),
    "immutable_file_coverage": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.persistence.immutable_file_coverage"),
    "revision_gap": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.persistence.revision_gap"),
}

def measure(name,observations):
    if name not in ALLOWED:raise ValueError('unknown measurement contract')
    module=_LOADERS[name]()
    return module.measure(observations)
