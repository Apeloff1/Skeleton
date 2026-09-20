"""Deterministic structural metrics for repository growth and organization."""
from __future__ import annotations

from dataclasses import dataclass
import math

from .model import RepositoryModel


@dataclass(frozen=True, slots=True)
class ZoneMetric:
    zone: str
    files: int
    lines: int
    bytes: int
    inbound_edges: int
    outbound_edges: int
    instability: float
    test_ratio: float
    line_share: float

    def as_dict(self) -> dict[str, object]:
        return {
            "zone": self.zone,
            "files": self.files,
            "lines": self.lines,
            "bytes": self.bytes,
            "inbound_edges": self.inbound_edges,
            "outbound_edges": self.outbound_edges,
            "instability": self.instability,
            "test_ratio": self.test_ratio,
            "line_share": self.line_share,
        }


@dataclass(frozen=True, slots=True)
class StructureMetrics:
    zones: tuple[ZoneMetric, ...]
    total_files: int
    total_lines: int
    total_bytes: int
    coupling_edges: int
    cycle_count: int
    largest_zone_line_share: float
    zone_entropy: float
    unclassified_ratio: float

    def as_dict(self) -> dict[str, object]:
        return {
            "zones": [item.as_dict() for item in self.zones],
            "total_files": self.total_files,
            "total_lines": self.total_lines,
            "total_bytes": self.total_bytes,
            "coupling_edges": self.coupling_edges,
            "cycle_count": self.cycle_count,
            "largest_zone_line_share": self.largest_zone_line_share,
            "zone_entropy": self.zone_entropy,
            "unclassified_ratio": self.unclassified_ratio,
        }


def structural_metrics(model: RepositoryModel) -> StructureMetrics:
    total_lines = sum(item.total_lines for item in model.subsystems)
    total_files = len(model.files)
    total_bytes = sum(item.total_bytes for item in model.subsystems)
    inbound: dict[str, int] = {}
    outbound: dict[str, int] = {}
    for edge in model.edges:
        outbound[edge.source] = outbound.get(edge.source, 0) + edge.evidence_count
        inbound[edge.target] = inbound.get(edge.target, 0) + edge.evidence_count

    zones: list[ZoneMetric] = []
    shares: list[float] = []
    for subsystem in model.subsystems:
        inc = inbound.get(subsystem.name, 0)
        out = outbound.get(subsystem.name, 0)
        denom = inc + out
        instability = out / denom if denom else 0.0
        test_ratio = subsystem.test_files / max(1, subsystem.code_files)
        share = subsystem.total_lines / max(1, total_lines)
        shares.append(share)
        zones.append(ZoneMetric(
            zone=subsystem.name,
            files=subsystem.file_count,
            lines=subsystem.total_lines,
            bytes=subsystem.total_bytes,
            inbound_edges=inc,
            outbound_edges=out,
            instability=round(instability, 6),
            test_ratio=round(test_ratio, 6),
            line_share=round(share, 6),
        ))

    entropy = 0.0
    for share in shares:
        if share > 0:
            entropy -= share * math.log2(share)
    normalized_entropy = entropy / math.log2(max(2, len(shares)))

    return StructureMetrics(
        zones=tuple(sorted(zones, key=lambda item: item.zone)),
        total_files=total_files,
        total_lines=total_lines,
        total_bytes=total_bytes,
        coupling_edges=sum(edge.evidence_count for edge in model.edges),
        cycle_count=len(model.cycles),
        largest_zone_line_share=round(max(shares, default=0.0), 6),
        zone_entropy=round(normalized_entropy, 6),
        unclassified_ratio=round(model.unclassified_count / max(1, total_files), 6),
    )
