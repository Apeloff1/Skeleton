"""Exact combinatorial indexing for the playable million-configuration game forge.

10,240 prior authored-law crossings × 10 mechanical play forms = 102,400
mode-bound foundations. Each × 12 stateful continuation contracts = 1,228,800
advanced configurations. 1.2m is a *structured* namespace, not a count of
separately written fiction, native builds or gameplay-quality certifications.
Everything is lazy O(1) unranking; no giant list, style multiplier or seed
inflation. Existing 10,240 foundation indices are never renumbered.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json

from .original_foundation_compiler import (
    FoundationError, FoundationLaw, ROOT_COUNT, REGIME_COUNT,
    STRUCTURED_FOUNDATIONS, INDEPENDENTLY_AUTHORED_ROOT_WORLDS,
    foundation_at,
)
from .original_world_play_forms import (
    PLAY_FORMS, PROGRESSION_LAWS, PlayForm, ProgressionLaw,
)

ADVANCED_VERSION = "original-world-million-forge.v1"
PLAY_FORM_COUNT = len(PLAY_FORMS)
ARC_COUNT = len(PROGRESSION_LAWS)
MODE_FOUNDATIONS = STRUCTURED_FOUNDATIONS * PLAY_FORM_COUNT
ADVANCED_CONFIGURATIONS = MODE_FOUNDATIONS * ARC_COUNT
FOUNDATIONS_THRESHOLD = 100_000
CONFIGURATIONS_THRESHOLD = 1_000_000
AUTHORSHIP_LABEL = "composed-authored-laws-with-executable-modes"


@dataclass(frozen=True)
class ModeFoundation:
    mode_index: int
    mode_id: str
    base: FoundationLaw
    form: PlayForm
    source: str = AUTHORSHIP_LABEL
    runtime_status: str = "bounded-genre-adapter"

    def as_dict(self) -> dict:
        return {
            "mode_index": str(self.mode_index),
            "mode_id": self.mode_id,
            "base_id": self.base.foundation_id,
            "base_index": str(self.base.foundation_index),
            "form": asdict(self.form),
            "source": self.source,
            "runtime_status": self.runtime_status,
            "version": ADVANCED_VERSION,
        }


@dataclass(frozen=True)
class AdvancedWorld:
    index: int
    advanced_id: str
    design_id: str
    mode: ModeFoundation
    arc: ProgressionLaw
    causal_contract: str
    decision_contract: str
    hazard_contract: str
    provenance: str = AUTHORSHIP_LABEL
    simulation_status: str = "bounded-reference-game-not-bespoke-realization"

    def as_dict(self) -> dict:
        return {
            "index": str(self.index),
            "advanced_id": self.advanced_id,
            "design_id": self.design_id,
            "mode": self.mode.as_dict(),
            "arc": asdict(self.arc),
            "causal_contract": self.causal_contract,
            "decision_contract": self.decision_contract,
            "hazard_contract": self.hazard_contract,
            "provenance": self.provenance,
            "simulation_status": self.simulation_status,
            "version": ADVANCED_VERSION,
        }


def _digest(value: dict) -> str:
    return sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def mode_at(index: int) -> ModeFoundation:
    if type(index) is not int or not 0 <= index < MODE_FOUNDATIONS:
        raise FoundationError("mode foundation index must be in [0,102399]")
    root_index, form_index = divmod(index, PLAY_FORM_COUNT)
    root, form = foundation_at(root_index), PLAY_FORMS[form_index]
    return ModeFoundation(
        index, f"mode-{root.foundation_id}-{form.form_id}", root, form,
    )


def advanced_at(index: int) -> AdvancedWorld:
    if type(index) is not int or not 0 <= index < ADVANCED_CONFIGURATIONS:
        raise FoundationError("advanced game configuration index outside capacity")
    mode_index, arc_index = divmod(index, ARC_COUNT)
    mode, arc = mode_at(mode_index), PROGRESSION_LAWS[arc_index]
    base, form = mode.base, mode.form
    signature = {
        "version": ADVANCED_VERSION,
        "original_root": base.root.root_id,
        "authored_regime": base.regime.regime_id,
        "authored_coupling": base.coupling,
        "play_form": form.form_id,
        "continuation": arc.arc_id,
    }
    return AdvancedWorld(
        index,
        f"adv-{index:07d}",
        _digest(signature),
        mode,
        arc,
        causal_contract=(
            f"{base.root.invariant}. {base.regime.invariant}. "
            f"{base.coupling} Gameplay: {form.control_law}. "
            f"Continuation: {arc.causal_contract}."
        ),
        decision_contract=(
            f"{base.player_lever} {form.player_loop}. {arc.player_agency}."
        ),
        hazard_contract=(
            f"{base.failure_pressure} {form.difficulty_pressure}. "
            f"{arc.setback_law}."
        ),
    )


def advanced_for(
    base_index: int, form_id: str, arc_id: str
) -> AdvancedWorld:
    if type(base_index) is not int or not 0 <= base_index < STRUCTURED_FOUNDATIONS:
        raise FoundationError("invalid base foundation selector")
    form = next((i for i, entry in enumerate(PLAY_FORMS)
                 if entry.form_id == form_id), None)
    arc = next((i for i, entry in enumerate(PROGRESSION_LAWS)
                if entry.arc_id == arc_id), None)
    if form is None or arc is None:
        raise FoundationError("unrecognized gameplay structure or continuation policy")
    return advanced_at((base_index * PLAY_FORM_COUNT + form) * ARC_COUNT + arc)


def advanced_from_seed(seed: str) -> AdvancedWorld:
    if not isinstance(seed, str) or not 0 < len(seed.encode("utf-8")) <= 4096:
        raise FoundationError("invalid advanced-world seed")
    raw = sha256((ADVANCED_VERSION + ":" + seed).encode("utf-8")).digest()
    return advanced_at(int.from_bytes(raw, "big") % ADVANCED_CONFIGURATIONS)


def advanced_from_id(value: str) -> AdvancedWorld:
    if not isinstance(value, str) or not value.startswith("adv-"):
        raise FoundationError("unknown advanced configuration")
    number = value[4:]
    if len(number) != 7 or not number.isascii() or not number.isdecimal():
        raise FoundationError("invalid advanced identifier")
    entry = advanced_at(int(number))
    if entry.advanced_id != value:
        raise FoundationError("noncanonical advanced identifier")
    return entry


def page_advanced(*, start: int = 0, limit: int = 24):
    if (type(start) is not int or type(limit) is not int or
            not 0 <= start <= ADVANCED_CONFIGURATIONS or
            not 1 <= limit <= 256):
        raise FoundationError("advanced paging requires bounded limits")
    for index in range(start, min(start + limit, ADVANCED_CONFIGURATIONS)):
        yield advanced_at(index)


def advanced_inventory() -> dict:
    return {
        "version": ADVANCED_VERSION,
        "base_authored_law_crossings": STRUCTURED_FOUNDATIONS,
        "separately_authored_root_premises": INDEPENDENTLY_AUTHORED_ROOT_WORLDS,
        "new_authored_play_form_templates": PLAY_FORM_COUNT,
        "new_authored_progression_contracts": ARC_COUNT,
        "mechanically_mode_bound_foundation_entries": MODE_FOUNDATIONS,
        "advanced_structured_configuration_entries": ADVANCED_CONFIGURATIONS,
        "exceeds_100k_composed_foundations": MODE_FOUNDATIONS >= FOUNDATIONS_THRESHOLD,
        "exceeds_1m_advanced_configurations": ADVANCED_CONFIGURATIONS >= CONFIGURATIONS_THRESHOLD,
        "style_hardware_era_or_seed_multipliers": 0,
        "individually_handwritten_advanced_worlds": 0,
        "fully_native_verified_games": 0,
        "all_compositions_share_an_abstract_reference_runtime": True,
        "index_ranges_are_mutually_nested_not_additive": True,
        "distinct_authored_content_guaranteed_for_each_index": False,
    }


assert MODE_FOUNDATIONS == 102_400
assert ADVANCED_CONFIGURATIONS == 1_228_800
