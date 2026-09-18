"""Static build audits.

This package is additive. Hidden network-command classification lives in
``network_audit``. Content-addressed incremental graph compilation (#940)
is a sibling concern and is not defined here.
"""

from skeleton.build.network_audit import (
    CLASSIFICATION_NETWORK_REQUIRED,
    CLASSIFICATION_NETWORK_UNKNOWN,
    CLASSIFICATION_OFFLINE,
    CONFLICT_DOMAIN,
    KIND,
    SCHEMA_VERSION,
    TASK_KEY,
    CommandFinding,
    NetworkAuditReport,
    audit_repository,
    classify_action_ref,
    classify_command,
    network_audit_snapshot,
)

__all__ = [
    "CLASSIFICATION_NETWORK_REQUIRED",
    "CLASSIFICATION_NETWORK_UNKNOWN",
    "CLASSIFICATION_OFFLINE",
    "CONFLICT_DOMAIN",
    "KIND",
    "SCHEMA_VERSION",
    "TASK_KEY",
    "CommandFinding",
    "NetworkAuditReport",
    "audit_repository",
    "classify_action_ref",
    "classify_command",
    "network_audit_snapshot",
]
