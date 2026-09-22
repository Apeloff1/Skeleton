"""System access contracts and schedule-side capability validation."""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from .canonical import digest
from .errors import ScheduleError, ValidationError
from .schedule import ExecutionPlan, SystemGraph, SystemSpec

_ACCESS_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")


class AccessMode(str, Enum):
    READ = "read"
    WRITE = "write"


@dataclass(frozen=True, order=True)
class AccessKey:
    namespace: str
    name: str

    def __post_init__(self) -> None:
        if not _ACCESS_RE.fullmatch(self.namespace):
            raise ValidationError("invalid access namespace")
        if not _ACCESS_RE.fullmatch(self.name):
            raise ValidationError("invalid access key name")

    @property
    def token(self) -> str:
        return f"{self.namespace}:{self.name}"

    @classmethod
    def parse(cls, token: str) -> "AccessKey":
        if not isinstance(token, str) or ":" not in token:
            raise ValidationError("access token must contain namespace separator")
        namespace, name = token.split(":", 1)
        return cls(namespace, name)


@dataclass(frozen=True)
class SystemAccessContract:
    system_id: str
    reads: tuple[AccessKey, ...]
    writes: tuple[AccessKey, ...]
    contract_digest: str

    @classmethod
    def from_spec(cls, spec: SystemSpec) -> "SystemAccessContract":
        reads = tuple(sorted(AccessKey.parse(token) for token in spec.reads))
        writes = tuple(sorted(AccessKey.parse(token) for token in spec.writes))
        material = {
            "system_id": spec.system_id,
            "reads": [key.token for key in reads],
            "writes": [key.token for key in writes],
        }
        return cls(spec.system_id, reads, writes, digest(material))


@dataclass(frozen=True)
class AccessConflict:
    first_system: str
    second_system: str
    key: str
    first_mode: AccessMode
    second_mode: AccessMode


@dataclass(frozen=True)
class AccessReport:
    contracts: tuple[SystemAccessContract, ...]
    conflicts: tuple[AccessConflict, ...]
    report_digest: str

    @property
    def conflict_free(self) -> bool:
        return not self.conflicts


class AccessAnalyzer:
    def __init__(self, graph: SystemGraph) -> None:
        if not isinstance(graph, SystemGraph):
            raise ValidationError("AccessAnalyzer requires SystemGraph")
        self.graph = graph

    def contracts(self) -> tuple[SystemAccessContract, ...]:
        return tuple(
            SystemAccessContract.from_spec(self.graph.get(system_id))
            for system_id in self.graph.system_ids()
        )

    def conflicts(self) -> tuple[AccessConflict, ...]:
        contracts = self.contracts()
        conflicts: list[AccessConflict] = []
        for index, left in enumerate(contracts):
            left_reads = {key.token for key in left.reads}
            left_writes = {key.token for key in left.writes}
            for right in contracts[index + 1 :]:
                right_reads = {key.token for key in right.reads}
                right_writes = {key.token for key in right.writes}
                for key in sorted(left_writes & right_writes):
                    conflicts.append(
                        AccessConflict(
                            left.system_id,
                            right.system_id,
                            key,
                            AccessMode.WRITE,
                            AccessMode.WRITE,
                        )
                    )
                for key in sorted(left_writes & right_reads):
                    conflicts.append(
                        AccessConflict(
                            left.system_id,
                            right.system_id,
                            key,
                            AccessMode.WRITE,
                            AccessMode.READ,
                        )
                    )
                for key in sorted(left_reads & right_writes):
                    conflicts.append(
                        AccessConflict(
                            left.system_id,
                            right.system_id,
                            key,
                            AccessMode.READ,
                            AccessMode.WRITE,
                        )
                    )
        return tuple(conflicts)

    def report(self) -> AccessReport:
        contracts = self.contracts()
        conflicts = self.conflicts()
        material = {
            "domain": "skeleton.simulation.ecs.access_report.v1",
            "contracts": [
                {
                    "system_id": contract.system_id,
                    "reads": [key.token for key in contract.reads],
                    "writes": [key.token for key in contract.writes],
                    "contract_digest": contract.contract_digest,
                }
                for contract in contracts
            ],
            "conflicts": [conflict.__dict__ for conflict in conflicts],
        }
        return AccessReport(contracts, conflicts, digest(material))

    def validate_plan(self, plan: ExecutionPlan | None = None) -> None:
        plan = plan or self.graph.plan()
        by_id = {contract.system_id: contract for contract in self.contracts()}
        for batch in plan.batches:
            ids = batch.system_ids
            for left_index, left_id in enumerate(ids):
                left = by_id[left_id]
                left_reads = {key.token for key in left.reads}
                left_writes = {key.token for key in left.writes}
                for right_id in ids[left_index + 1 :]:
                    right = by_id[right_id]
                    right_reads = {key.token for key in right.reads}
                    right_writes = {key.token for key in right.writes}
                    overlap = (
                        (left_writes & right_writes)
                        | (left_writes & right_reads)
                        | (left_reads & right_writes)
                    )
                    if overlap:
                        raise ScheduleError(
                            "execution batch contains conflicting access contracts",
                            context={
                                "batch": batch.index,
                                "left": left_id,
                                "right": right_id,
                                "keys": sorted(overlap),
                            },
                        )
