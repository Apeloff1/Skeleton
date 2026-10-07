"""Deterministic diagnostics for ECS worlds and execution plans.

Diagnostics are intentionally read-only.  They aggregate existing invariant,
query, schedule, partition and journal facts into stable findings that can be
stored as CI evidence or shown in editor tooling.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Iterable, Mapping

from .access import AccessAnalyzer
from .canonical import digest
from .errors import ValidationError
from .inspection import inspect_store
from .journal import MutationJournal
from .partitions import WorldPartitionIndex
from .schedule import SystemGraph
from .store import EntityStore
from .tables import TableRegistry


class DiagnosticSeverity(IntEnum):
    INFO = 10
    WARNING = 20
    ERROR = 30


@dataclass(frozen=True, order=True)
class DiagnosticFinding:
    severity: DiagnosticSeverity
    code: str
    subject: str
    message: str
    evidence: Mapping[str, Any]
    finding_digest: str

    @classmethod
    def make(
        cls,
        severity: DiagnosticSeverity,
        code: str,
        subject: str,
        message: str,
        evidence: Mapping[str, Any] | None = None,
    ) -> "DiagnosticFinding":
        if not isinstance(severity, DiagnosticSeverity):
            severity = DiagnosticSeverity(severity)
        for label, value in (("code", code), ("subject", subject), ("message", message)):
            if not isinstance(value, str) or not value:
                raise ValidationError(f"diagnostic {label} must be non-empty text")
        frozen = dict(evidence or {})
        material = {
            "severity": int(severity),
            "code": code,
            "subject": subject,
            "message": message,
            "evidence": frozen,
        }
        return cls(severity, code, subject, message, frozen, digest(material))


@dataclass(frozen=True)
class DiagnosticSummary:
    infos: int
    warnings: int
    errors: int
    total: int


@dataclass(frozen=True)
class DiagnosticReport:
    state_digest: str
    revision: int
    tick: int
    findings: tuple[DiagnosticFinding, ...]
    summary: DiagnosticSummary
    report_digest: str

    @property
    def ok(self) -> bool:
        return self.summary.errors == 0

    def by_code(self, code: str) -> tuple[DiagnosticFinding, ...]:
        return tuple(row for row in self.findings if row.code == code)

    def at_least(self, severity: DiagnosticSeverity) -> tuple[DiagnosticFinding, ...]:
        return tuple(row for row in self.findings if row.severity >= severity)


class DiagnosticBuilder:
    def __init__(self, store: EntityStore) -> None:
        if not isinstance(store, EntityStore):
            raise ValidationError("DiagnosticBuilder requires EntityStore")
        self.store = store
        self._findings: list[DiagnosticFinding] = []

    def add(
        self,
        severity: DiagnosticSeverity,
        code: str,
        subject: str,
        message: str,
        evidence: Mapping[str, Any] | None = None,
    ) -> DiagnosticFinding:
        row = DiagnosticFinding.make(severity, code, subject, message, evidence)
        self._findings.append(row)
        return row

    def check_store(self) -> "DiagnosticBuilder":
        try:
            self.store.assert_invariants()
        except Exception as exc:
            self.add(
                DiagnosticSeverity.ERROR,
                "STORE.INVARIANT",
                "store",
                "authoritative store invariant validation failed",
                {"error_type": type(exc).__name__, "message": str(exc)},
            )
            return self
        self.add(
            DiagnosticSeverity.INFO,
            "STORE.INVARIANT_OK",
            "store",
            "authoritative store invariants are valid",
            {
                "revision": self.store.revision,
                "entities": self.store.entity_count,
                "components": self.store.component_count,
            },
        )
        live = set(self.store.entity_ids())
        tombstoned = set(self.store.tombstone_ids())
        overlap = sorted(live & tombstoned)
        if overlap:
            self.add(
                DiagnosticSeverity.ERROR,
                "STORE.LIVE_TOMBSTONE_OVERLAP",
                "store",
                "entity ids are both live and tombstoned",
                {"entity_ids": overlap[:64], "count": len(overlap)},
            )
        empty = [entity_id for entity_id in self.store.entity_ids() if not self.store.component_ids(entity_id)]
        if empty:
            self.add(
                DiagnosticSeverity.INFO,
                "STORE.EMPTY_ENTITIES",
                "store",
                "world contains entities without components",
                {"count": len(empty), "first": empty[:32]},
            )
        return self

    def check_journal(self, journal: MutationJournal | None) -> "DiagnosticBuilder":
        if journal is None:
            return self
        if not isinstance(journal, MutationJournal):
            raise ValidationError("check_journal requires MutationJournal")
        verification = journal.verify()
        if verification.valid:
            self.add(
                DiagnosticSeverity.INFO,
                "JOURNAL.VALID",
                "journal",
                "journal digest chain verifies",
                {"entries": verification.entries, "head": verification.final_digest},
            )
        else:
            self.add(
                DiagnosticSeverity.ERROR,
                "JOURNAL.INVALID",
                "journal",
                "journal digest chain does not verify",
                {
                    "entries": verification.entries,
                    "sequence": verification.first_invalid_sequence,
                    "reason": verification.reason,
                },
            )
        return self

    def check_partitions(self, partitions: WorldPartitionIndex | None) -> "DiagnosticBuilder":
        if partitions is None:
            return self
        if not isinstance(partitions, WorldPartitionIndex):
            raise ValidationError("check_partitions requires WorldPartitionIndex")
        try:
            partitions.assert_invariants()
        except Exception as exc:
            self.add(
                DiagnosticSeverity.ERROR,
                "PARTITION.INVARIANT",
                "partitions",
                "partition index invariant validation failed",
                {"error_type": type(exc).__name__, "message": str(exc)},
            )
            return self
        snapshot = partitions.snapshot()
        self.add(
            DiagnosticSeverity.INFO,
            "PARTITION.VALID",
            "partitions",
            "partition index invariants are valid",
            {
                "partitions": len(snapshot.partitions),
                "assignments": snapshot.assignment_count,
                "unassigned": len(snapshot.unassigned),
            },
        )
        if snapshot.unassigned:
            self.add(
                DiagnosticSeverity.WARNING,
                "PARTITION.UNASSIGNED",
                "partitions",
                "live entities are not assigned to partitions",
                {"count": len(snapshot.unassigned), "first": snapshot.unassigned[:32]},
            )
        return self

    def check_tables(self, tables: TableRegistry | None) -> "DiagnosticBuilder":
        if tables is None:
            return self
        if not isinstance(tables, TableRegistry):
            raise ValidationError("check_tables requires TableRegistry")
        stale: list[str] = []
        for schema_id in tables.known_schema_ids():
            table = tables._tables[schema_id]
            if not table.is_current(self.store):
                stale.append(schema_id)
        if stale:
            self.add(
                DiagnosticSeverity.WARNING,
                "TABLE.STALE",
                "tables",
                "derived component tables are stale",
                {"schema_ids": stale},
            )
        else:
            self.add(
                DiagnosticSeverity.INFO,
                "TABLE.CURRENT",
                "tables",
                "all known component tables match current store state",
                {"tables": len(tables.known_schema_ids())},
            )
        return self

    def check_schedule(self, graph: SystemGraph | None) -> "DiagnosticBuilder":
        if graph is None:
            return self
        if not isinstance(graph, SystemGraph):
            raise ValidationError("check_schedule requires SystemGraph")
        try:
            plan = graph.plan()
        except Exception as exc:
            self.add(
                DiagnosticSeverity.ERROR,
                "SCHEDULE.INVALID",
                "schedule",
                "system graph cannot produce an execution plan",
                {"error_type": type(exc).__name__, "message": str(exc)},
            )
            return self
        self.add(
            DiagnosticSeverity.INFO,
            "SCHEDULE.PLAN",
            "schedule",
            "system graph produced deterministic execution plan",
            {
                "systems": len(plan.ordered_system_ids),
                "batches": len(plan.batches),
                "fingerprint": plan.fingerprint,
            },
        )
        try:
            AccessAnalyzer(graph).validate_plan(plan)
        except Exception as exc:
            self.add(
                DiagnosticSeverity.ERROR,
                "SCHEDULE.ACCESS_CONFLICT",
                "schedule",
                "execution plan violates declared access contracts",
                {"error_type": type(exc).__name__, "message": str(exc)},
            )
        return self

    def check_schema_usage(self) -> "DiagnosticBuilder":
        catalog = self.store.registry.catalog()
        registered = {row["schema_id"] for row in catalog}
        used: set[str] = set()
        for entity_id in self.store.entity_ids():
            used.update(self.store.component_ids(entity_id))
        unused = tuple(sorted(registered - used))
        missing = tuple(sorted(used - registered))
        if missing:
            self.add(
                DiagnosticSeverity.ERROR,
                "SCHEMA.MISSING",
                "schemas",
                "components reference unregistered schemas",
                {"schema_ids": missing},
            )
        if unused:
            self.add(
                DiagnosticSeverity.INFO,
                "SCHEMA.UNUSED",
                "schemas",
                "registered schemas are not currently used by live entities",
                {"schema_ids": unused},
            )
        return self

    def build(self) -> DiagnosticReport:
        inspection = inspect_store(self.store)
        rows = tuple(
            sorted(
                self._findings,
                key=lambda row: (-int(row.severity), row.code, row.subject, row.finding_digest),
            )
        )
        infos = sum(1 for row in rows if row.severity is DiagnosticSeverity.INFO)
        warnings = sum(1 for row in rows if row.severity is DiagnosticSeverity.WARNING)
        errors = sum(1 for row in rows if row.severity is DiagnosticSeverity.ERROR)
        summary = DiagnosticSummary(infos, warnings, errors, len(rows))
        material = {
            "domain": "skeleton.simulation.ecs.diagnostic_report.v1",
            "state_digest": self.store.state_digest,
            "revision": self.store.revision,
            "tick": self.store.tick,
            "findings": [row.finding_digest for row in rows],
            "summary": summary.__dict__,
            "inspection": inspection.inspection_digest,
        }
        return DiagnosticReport(
            state_digest=self.store.state_digest,
            revision=self.store.revision,
            tick=self.store.tick,
            findings=rows,
            summary=summary,
            report_digest=digest(material),
        )


def diagnose(
    store: EntityStore,
    *,
    journal: MutationJournal | None = None,
    partitions: WorldPartitionIndex | None = None,
    tables: TableRegistry | None = None,
    graph: SystemGraph | None = None,
) -> DiagnosticReport:
    return (
        DiagnosticBuilder(store)
        .check_store()
        .check_schema_usage()
        .check_journal(journal)
        .check_partitions(partitions)
        .check_tables(tables)
        .check_schedule(graph)
        .build()
    )
