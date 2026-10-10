"""Dated evolutionary game-design tracks across verified *catalog entries*.

Hardware company succession is a reference chronology, not proof of binary,
instruction-set, cartridge, IP or software compatibility. Every stage plans
an ORIGINAL homebrew transformation, never promotes binaries or assets.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from types import MappingProxyType
from typing import Mapping
import json
import re

from .platform_registry import PlatformRegistry, default_registry
from .port_planner import (
    HomebrewSource, PortBlueprint, PortMode, PortPlanningError,
    PortRequest, compile_port,
)

_ID = re.compile(r"^[a-z][a-z0-9_]+$")
_SIGNAL = re.compile(r"^[a-z0-9][a-z0-9_]{1,70}$")
_MIN_YEAR, _MAX_YEAR = 1800, 2100


class GameEvolutionError(ValueError):
    """Unsafe, circular or unsupported hardware-evolution path."""


@dataclass(frozen=True, slots=True)
class EvolutionNode:
    platform_id: str
    year: int
    lineage: str
    predecessor: str | None
    design_signals: tuple[str, ...]
    chronology_confidence: str


@dataclass(frozen=True, slots=True)
class EvolutionArchive:
    nodes: Mapping[str, EvolutionNode]
    schema_version: int
    evidence_sources: tuple[str, ...]

    def get(self, platform_id: str) -> EvolutionNode:
        try:
            return self.nodes[platform_id]
        except (TypeError, KeyError) as exc:
            raise GameEvolutionError("platform has no curated chronology: " + str(platform_id)) from exc

    def lineage_members(self, lineage: str) -> tuple[EvolutionNode, ...]:
        return tuple(sorted(
            (node for node in self.nodes.values() if node.lineage == lineage),
            key=lambda n: (n.year, n.platform_id),
        ))

    def progress(self, start: str, destination: str, *, reverse: bool = False) -> tuple[EvolutionNode, ...]:
        """Find a single *documented succession chain*; arbitrary cross-era ports
        remain available through the independent port planner.
        """
        self.get(start)
        self.get(destination)
        if start == destination:
            raise GameEvolutionError("evolution requires a change of platform")
        current = self.get(destination if not reverse else start)
        expected = start if not reverse else destination
        reversed_path = [current]
        while current.platform_id != expected:
            if current.predecessor is None:
                raise GameEvolutionError("no documented predecessor route")
            current = self.get(current.predecessor)
            reversed_path.append(current)
        path = tuple(reversed(reversed_path))
        return tuple(reversed(path)) if reverse else path

    def summary(self) -> dict[str, object]:
        lineages: dict[str, int] = {}
        for node in self.nodes.values():
            lineages[node.lineage] = lineages.get(node.lineage, 0) + 1
        return {
            "schema_version": self.schema_version,
            "historical_nodes": len(self.nodes),
            "lineages": dict(sorted(lineages.items())),
            "earliest_year": min(n.year for n in self.nodes.values()),
            "latest_year": max(n.year for n in self.nodes.values()),
            "native_export_attestations": 0,
            "source_citations_per_individual_record_verified": False,
            "global_archive_complete": False,
        }


def parse_evolution_archive(document: str | bytes, registry: PlatformRegistry | None = None) -> EvolutionArchive:
    registry = default_registry() if registry is None else registry
    if not isinstance(registry, PlatformRegistry):
        raise GameEvolutionError("validated registry required")
    try:
        raw = json.loads(document)
    except (TypeError, ValueError) as exc:
        raise GameEvolutionError("invalid chronology JSON") from exc
    if not isinstance(raw, dict) or type(raw.get("schema_version")) is not int or raw["schema_version"] != 1:
        raise GameEvolutionError("unsupported chronology schema")
    sources = raw.get("evidence_sources")
    if not isinstance(sources, list) or not sources or any(
        not isinstance(s, str) or not s.startswith("https://") or len(s) > 250 for s in sources
    ):
        raise GameEvolutionError("archival reference locations are required")
    records = raw.get("nodes")
    if not isinstance(records, list) or not records:
        raise GameEvolutionError("empty chronology")
    entries: dict[str, EvolutionNode] = {}
    for item in records:
        if not isinstance(item, dict):
            raise GameEvolutionError("malformed chronology entry")
        id_ = item.get("platform_id")
        parent = item.get("predecessor")
        year = item.get("first_year")
        lineage = item.get("lineage")
        signals = item.get("design_signals")
        confidence = item.get("chronology_confidence")
        if not isinstance(id_, str) or id_ not in registry.profiles or id_ in entries:
            raise GameEvolutionError("invalid, unknown or duplicate dated platform")
        if type(year) is not int or not _MIN_YEAR <= year <= _MAX_YEAR:
            raise GameEvolutionError("chronology requires an explicit bounded year")
        if not isinstance(lineage, str) or not _ID.fullmatch(lineage):
            raise GameEvolutionError("invalid lineage key")
        if parent is not None and (not isinstance(parent, str) or parent == id_):
            raise GameEvolutionError("invalid chronology predecessor")
        if (
            not isinstance(signals, list) or not 1 <= len(signals) <= 20
            or any(not isinstance(s, str) or not _SIGNAL.fullmatch(s) for s in signals)
            or len(set(signals)) != len(signals)
        ):
            raise GameEvolutionError("invalid or duplicate design traits")
        if confidence != "reference_era_requires_individual_source_confirmation":
            raise GameEvolutionError("date evidence must not be self-certified")
        entries[id_] = EvolutionNode(id_, year, lineage, parent, tuple(signals), confidence)
    for node in entries.values():
        if node.predecessor is None:
            continue
        earlier = entries.get(node.predecessor)
        if earlier is None or earlier.lineage != node.lineage or earlier.year >= node.year:
            raise GameEvolutionError("missing, cross-lineage or time-travel predecessor")
    return EvolutionArchive(
        MappingProxyType(dict(sorted(entries.items()))), 1, tuple(sources),
    )


@lru_cache(maxsize=1)
def default_evolution_archive() -> EvolutionArchive:
    raw = files("skeleton.ai.game_builder").joinpath("evolution_lineages.json").read_text(encoding="utf-8")
    return parse_evolution_archive(raw)


@dataclass(frozen=True, slots=True)
class EvolutionStage:
    stage_number: int
    from_platform: str
    to_platform: str
    source_year: int
    target_year: int
    unlocked_design_signals: tuple[str, ...]
    retained_identity: tuple[str, ...]
    mode: str
    adaptation: PortBlueprint
    native_export_verified: bool = False


@dataclass(frozen=True, slots=True)
class EvolutionCampaign:
    original_project_id: str
    campaign_kind: str
    stages: tuple[EvolutionStage, ...]
    rights_evidence_sha256: str
    generated_games_count: int = 0
    native_binaries_built: int = 0

    def requirements(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(
            probe for stage in self.stages for probe in stage.adaptation.acceptance_probes
        ))


def plan_evolution_campaign(
    source: HomebrewSource, destination: str, *, reverse: bool = False,
    archive: EvolutionArchive | None = None, registry: PlatformRegistry | None = None,
) -> EvolutionCampaign:
    """Create a directed game-evolution lesson track bound to homebrew rights."""
    if not isinstance(source, HomebrewSource):
        raise GameEvolutionError("owned/cleared homebrew required")
    if type(reverse) is not bool:
        raise GameEvolutionError("reverse flag must be boolean")
    registry = default_registry() if registry is None else registry
    archive = default_evolution_archive() if archive is None else archive
    if not isinstance(registry, PlatformRegistry) or not isinstance(archive, EvolutionArchive):
        raise GameEvolutionError("validated archive and registry required")
    sequence = archive.progress(source.platform_id, destination, reverse=reverse)
    mode = PortMode.REVERSE_CONSTRAINED if reverse else PortMode.ENHANCED
    stages = []
    accumulated_signals: set[str] = set()
    for index, (before, after) in enumerate(zip(sequence, sequence[1:]), start=1):
        new_signals = tuple(signal for signal in after.design_signals if signal not in accumulated_signals)
        accumulated_signals.update(before.design_signals)
        accumulated_signals.update(new_signals)
        try:
            adaptation = compile_port(PortRequest((source,), after.platform_id, mode), registry=registry)
        except PortPlanningError as exc:
            raise GameEvolutionError("port planner declined campaign stage") from exc
        stages.append(EvolutionStage(
            stage_number=index, from_platform=before.platform_id, to_platform=after.platform_id,
            source_year=before.year, target_year=after.year,
            unlocked_design_signals=new_signals, retained_identity=source.creative_identity,
            mode=mode.value, adaptation=adaptation,
        ))
    return EvolutionCampaign(
        source.project_id,
        "historical_reverse_constraint" if reverse else "historical_style_evolution",
        tuple(stages), source.evidence_sha256,
    )


def archive_coverage_report(
    registry: PlatformRegistry | None = None, archive: EvolutionArchive | None = None,
) -> dict[str, object]:
    """No global '100%' illusion: disclose absent per-platform chronology and SDKs."""
    registry = default_registry() if registry is None else registry
    archive = default_evolution_archive() if archive is None else archive
    missing = tuple(sorted(set(registry.profiles) - set(archive.nodes)))
    return {
        "catalogued_platform_records": len(registry.profiles),
        "dated_evolution_example_records": len(archive.nodes),
        "undated_or_unlinked_catalogue_records": len(missing),
        "undated_or_unlinked_platform_ids": missing,
        "independent_record_level_references_verified": 0,
        "native_platform_toolchains_verified": 0,
        "historical_universe_denominator": None,
        "complete_historical_census": False,
        "completion_policy": "No completeness percentage without a defined universe and verified primary-source reconciliation.",
    }
