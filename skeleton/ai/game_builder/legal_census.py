"""Complete *coverage of catalogued records* for rights/audit questions.

This audit includes every current platform without asserting that the archive
contains every machine ever made. It is intentionally NOT a legal clearance
decision for individual platform owners or historic game rights.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .platform_registry import PlatformRegistry, default_registry
from .evolution_archive import EvolutionArchive, default_evolution_archive

_COMMON = (
    "independent_game_authorship",
    "third_party_code_art_audio_and_character_rights",
    "trademark_and_distribution_presentation",
    "jurisdiction_and_current_statutory_exceptions",
    "hardware_tpm_or_secure_boot_conditions",
    "sdk_and_distribution_channel_terms",
    "physical_hardware_or_emulator_validation",
)
_PLATFORM_QUESTIONS = {
    "console": ("cartridge_disc_signature_or_boot_requirements", "controller_and_save_hardware"),
    "handheld": ("portable_firmware_and_screen_interface", "cartridge_or_signed_package_rights"),
    "computer": ("historical_os_and_native_abi", "rom_bios_firmware_dependencies"),
    "arcade": ("board_and_io_protocols", "cabinet_operator_constraints"),
    "calculator": ("calculator_firmware_api_and_program_format",),
    "mobile": ("app_distribution_agreement", "runtime_and_signed_package_format"),
    "micro": ("firmware_interface_rights_and_board_license",),
    "fantasy": ("virtual_console_runtime_and_cartridge_format_license",),
    "educational": ("licensed_toy_or_learning_platform_interfaces",),
    "precursor": ("noncommercial_research_apparatus_and_patent",),
    "electromechanical": ("mechanical_actuator_electrical_safety_and_patent",),
    "mechanical": ("physical_mechanism_patent_and_product_safety",),
}


@dataclass(frozen=True, slots=True)
class HistoricalRightsCandidate:
    platform_id: str
    kind: str
    lifecycle: str
    dated_design_lineage: bool
    research_status: str
    native_toolchain_status: str
    legal_release_status: str
    review_questions: tuple[str, ...]
    design_inspiration_available: bool = True
    lawful_downloadable_game_supplied: bool = False
    platform_license_automatically_required_for_independent_game_ideas: bool = False
    distribution_cleared: bool = False


@dataclass(frozen=True, slots=True)
class HistoricalRightsCensus:
    records: Mapping[str, HistoricalRightsCandidate]
    historical_global_denominator: int | None = None

    def summary(self) -> dict[str, object]:
        by_kind: dict[str, int] = {}
        for v in self.records.values():
            by_kind[v.kind] = by_kind.get(v.kind, 0) + 1
        return {
            "catalogued_record_count": len(self.records),
            "categories": dict(sorted(by_kind.items())),
            "dated_sample_records": sum(p.dated_design_lineage for p in self.records.values()),
            "target_specific_legal_reviews_completed": 0,
            "native_toolchains_with_evidence": 0,
            "game_rights_licenses_automatically_conferred": 0,
            "independent_homebrew_design_inspirations": len(self.records),
            "legal_release_certifications": 0,
            "global_historical_universe_denominator": self.historical_global_denominator,
            "claim_of_global_archive_completeness": False,
        }

    def select(self, *, kind: str | None = None, only_undated: bool = False) -> tuple[HistoricalRightsCandidate, ...]:
        return tuple(
            item for item in self.records.values()
            if (kind is None or item.kind == kind)
            and (not only_undated or not item.dated_design_lineage)
        )


def catalog_rights_census(
    registry: PlatformRegistry | None = None,
    chronology: EvolutionArchive | None = None,
) -> HistoricalRightsCensus:
    """Every catalogued platform gets explicit unresolved legal/SDK questions."""
    registry = default_registry() if registry is None else registry
    chronology = default_evolution_archive() if chronology is None else chronology
    if not isinstance(registry, PlatformRegistry) or not isinstance(chronology, EvolutionArchive):
        raise TypeError("validated catalogue and chronology required")
    unknown_kinds = {p.kind for p in registry.profiles.values()} - set(_PLATFORM_QUESTIONS)
    if unknown_kinds:
        raise ValueError("no policy question list for historical hardware kind")
    records = {
        p.id: HistoricalRightsCandidate(
            platform_id=p.id,
            kind=p.kind,
            lifecycle=p.lifecycle,
            dated_design_lineage=p.id in chronology.nodes,
            research_status=p.research_status,
            native_toolchain_status=p.toolchain_status,
            legal_release_status="unreviewed_requires_case_specific_authority",
            review_questions=(*_COMMON, *_PLATFORM_QUESTIONS[p.kind]),
        )
        for p in registry.profiles.values()
    }
    return HistoricalRightsCensus(MappingProxyType(records))
