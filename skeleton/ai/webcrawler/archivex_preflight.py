"""ArchiveX research subsystem preflight and consistency diagnostics.

Preflight is intentionally read-only. It identifies schema drift, orphaned
evidence, unindexed promoted claims, consumed approvals without knowledge,
and invalid memory digests. Results are owner-scoped and deterministic.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import sqlite3

from .archivex_knowledge import ArchiveXKnowledgeStore


class DiagnosticSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class DiagnosticPolicy:
    max_rows_per_table: int = 10000
    max_issues: int = 500
    require_dependency_index: bool = True


@dataclass(frozen=True)
class DiagnosticIssue:
    severity: DiagnosticSeverity
    code: str
    record_id: str
    message: str


@dataclass(frozen=True)
class DiagnosticReport:
    owner: str
    checked_records: int
    issues: tuple[DiagnosticIssue, ...]
    truncated: bool
    fingerprint: str

    @property
    def healthy(self) -> bool:
        return not self.truncated and not any(
            issue.severity is DiagnosticSeverity.ERROR
            for issue in self.issues
        )


class ArchiveXPreflight:
    def __init__(self, db: sqlite3.Connection,
                 knowledge: ArchiveXKnowledgeStore,
                 *, policy: DiagnosticPolicy = DiagnosticPolicy()):
        if db is not knowledge.db:
            raise ValueError("preflight requires the knowledge database")
        if not 1 <= policy.max_rows_per_table <= 1000000:
            raise ValueError("invalid scan budget")
        if not 1 <= policy.max_issues <= 100000:
            raise ValueError("invalid issue budget")
        self.db = db
        self.knowledge = knowledge
        self.policy = policy

    def _tables(self) -> set[str]:
        return {
            row[0] for row in self.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

    def scan(self, owner: str, *, authorized: bool) -> DiagnosticReport:
        if not authorized:
            raise PermissionError("archive diagnostics require authorization")
        owner = self.knowledge._owner(owner)
        tables = self._tables()
        required = {
            "archivex_snapshots", "archivex_evidence_anchors",
            "archivex_promotions", "archivex_knowledge",
        }
        if self.policy.require_dependency_index:
            required.add("archivex_dependencies")
        issues = []
        checked = 0
        truncated = False

        def emit(severity, code, record_id, message):
            nonlocal truncated
            if len(issues) >= self.policy.max_issues:
                truncated = True
                return
            issues.append(DiagnosticIssue(severity, code, record_id, message))

        for table in sorted(required - tables):
            emit(DiagnosticSeverity.ERROR, "SCHEMA_MISSING", table,
                 "required archive table missing")
        if "archivex_knowledge" in tables:
            count = self.db.execute(
                "SELECT COUNT(*) FROM archivex_knowledge WHERE owner=?",
                (owner,),
            ).fetchone()[0]
            if count > self.policy.max_rows_per_table:
                truncated = True
            rows = self.db.execute("""
                SELECT claim_id, active FROM archivex_knowledge
                WHERE owner=? ORDER BY claim_id LIMIT ?
            """, (owner, self.policy.max_rows_per_table)).fetchall()
            for claim_id, active in rows:
                checked += 1
                try:
                    memory = self.knowledge.read(
                        owner, claim_id, authorized=True,
                        include_inactive=True,
                    )
                except (ValueError, TypeError, json.JSONDecodeError):
                    emit(DiagnosticSeverity.ERROR, "KNOWLEDGE_TAMPERED",
                         claim_id, "knowledge integrity check failed")
                    continue
                if memory is None:
                    emit(DiagnosticSeverity.ERROR, "KNOWLEDGE_MISSING",
                         claim_id, "indexed knowledge row missing")
                    continue
                if active and "archivex_dependencies" in tables:
                    indexed = {
                        row[0] for row in self.db.execute("""
                            SELECT evidence_id FROM archivex_dependencies
                            WHERE owner=? AND claim_id=?
                        """, (owner, claim_id))
                    }
                    if indexed != set(memory.evidence_ids):
                        emit(DiagnosticSeverity.ERROR, "DEPENDENCY_MISMATCH",
                             claim_id, "active knowledge has missing or extra dependencies")
                if active and "archivex_evidence_anchors" in tables:
                    anchored = {
                        row[0] for row in self.db.execute("""
                            SELECT evidence_id FROM archivex_evidence_anchors
                            WHERE owner=? AND claim_id=?
                        """, (owner, claim_id))
                    }
                    if not set(memory.evidence_ids).issubset(anchored):
                        emit(DiagnosticSeverity.ERROR, "ANCHOR_MISSING",
                             claim_id, "promoted evidence has missing anchors")
        if "archivex_promotions" in tables and "archivex_knowledge" in tables:
            count = self.db.execute("""
                SELECT COUNT(*) FROM archivex_promotions
                WHERE owner=? AND consumed_at IS NOT NULL
            """, (owner,)).fetchone()[0]
            if count > self.policy.max_rows_per_table:
                truncated = True
            rows = self.db.execute("""
                SELECT p.claim_id FROM archivex_promotions p
                LEFT JOIN archivex_knowledge k
                  ON k.owner=p.owner AND k.claim_id=p.claim_id
                WHERE p.owner=? AND p.consumed_at IS NOT NULL
                  AND k.claim_id IS NULL
                ORDER BY p.claim_id LIMIT ?
            """, (owner, self.policy.max_rows_per_table)).fetchall()
            checked += len(rows)
            for (claim_id,) in rows:
                emit(DiagnosticSeverity.ERROR, "ORPHANED_APPROVAL",
                     claim_id, "consumed promotion has no knowledge record")
        ordered = tuple(sorted(
            issues, key=lambda issue: (
                issue.severity.value, issue.code, issue.record_id,
            ),
        ))
        fingerprint = sha256(json.dumps(
            [(i.severity.value, i.code, i.record_id) for i in ordered],
            separators=(",", ":"), ensure_ascii=True,
        ).encode()).hexdigest()
        return DiagnosticReport(owner, checked, ordered, truncated, fingerprint)
