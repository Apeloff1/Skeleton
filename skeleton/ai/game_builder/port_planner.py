"""Deterministic homebrew-first cross-era port blueprints.

These are reproducible design/transformation plans, NOT emulator invocation,
native toolchain support, firmware extraction, commercial-ROM migration or legal
clearance. Native release qualification remains a separate fail-closed workflow.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import re

from .platform_registry import PlatformProfile, PlatformRegistry, PlatformRegistryError, default_registry

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_VALID_RIGHTS = frozenset({"project_owned", "licensed_homebrew", "public_domain_homebrew"})


class PortPlanningError(ValueError):
    """A requested port violates technical or evidence admission rules."""


class PortMode(str, Enum):
    FAITHFUL = "faithful"
    ENHANCED = "enhanced"
    CROSS_HYBRID = "cross_hybrid"
    REVERSE_CONSTRAINED = "reverse_constrained"


@dataclass(frozen=True, slots=True)
class HomebrewSource:
    """Evidence references are never proof of independent rights verification."""
    project_id: str
    platform_id: str
    rights_basis: str
    evidence_sha256: str
    creative_identity: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.project_id, str) or not self.project_id.strip():
            raise PortPlanningError("source project must be identified")
        if self.rights_basis not in _VALID_RIGHTS:
            raise PortPlanningError("non-homebrew or unknown-rights source refused")
        if not isinstance(self.evidence_sha256, str) or not _SHA256.fullmatch(self.evidence_sha256):
            raise PortPlanningError("source must have content-specific SHA256 rights evidence")
        if (
            not isinstance(self.creative_identity, tuple) or not self.creative_identity
            or any(not isinstance(v, str) or not v.strip() for v in self.creative_identity)
        ):
            raise PortPlanningError("creative identity must be explicit")
        if len(set(self.creative_identity)) != len(self.creative_identity):
            raise PortPlanningError("duplicate creative identity invariants")


@dataclass(frozen=True, slots=True)
class PortRequest:
    sources: tuple[HomebrewSource, ...]
    target_platform_id: str
    mode: PortMode = PortMode.FAITHFUL

    def __post_init__(self) -> None:
        if not isinstance(self.mode, PortMode):
            raise PortPlanningError("unknown port mode")
        if not isinstance(self.sources, tuple):
            raise PortPlanningError("sources must be a tuple")
        needed = 2 if self.mode is PortMode.CROSS_HYBRID else 1
        if len(self.sources) != needed or any(not isinstance(s, HomebrewSource) for s in self.sources):
            raise PortPlanningError("cross-hybrid needs two independently cleared homebrew sources; other modes need one")
        if len({s.project_id for s in self.sources}) != len(self.sources):
            raise PortPlanningError("hybrid sources must be distinct projects")
        if not isinstance(self.target_platform_id, str) or not self.target_platform_id:
            raise PortPlanningError("target platform is required")


@dataclass(frozen=True, slots=True)
class PortAction:
    phase: str
    disposition: str
    work: str


@dataclass(frozen=True, slots=True)
class PortBlueprint:
    schema_version: int
    source_platform_ids: tuple[str, ...]
    target_platform_id: str
    mode: str
    design_intent: tuple[str, ...]
    target_constraints: tuple[str, ...]
    actions: tuple[PortAction, ...]
    acceptance_probes: tuple[str, ...]
    pending_release_gates: tuple[str, ...]
    planning_status: str
    digest: str

    @property
    def native_build_verified(self) -> bool:
        return False

    @property
    def releasable(self) -> bool:
        return False


def _deterministic_digest(payload: dict[str, object]) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(data.encode("utf-8")).hexdigest()


def _actions(target: PlatformProfile, sources: tuple[PlatformProfile, ...], mode: PortMode) -> tuple[PortAction, ...]:
    source_tier = max(p.tier for p in sources)
    expanding = target.tier > source_tier
    reducing = target.tier < source_tier
    hybrid = mode is PortMode.CROSS_HYBRID
    stages = [
        PortAction("mechanics", "preserve", "Retain original game loop, causal rules and player-facing feel; document authorized sources"),
        PortAction("render", "rebuild", "Map authored art into target " + target.render + " renderer; preserve composition, shape language and legibility"),
        PortAction("audio", "adapt", "Rescore or resynthesize original/cleared music for " + target.sound + " without copying third-party masters"),
        PortAction("input", "adapt", "Transform inputs into " + target.input + " and retain equivalent timing and affordances"),
        PortAction("performance", "budget", "Schedule frame, memory, storage and streaming budgets against the actual target hardware profile"),
        PortAction("storage", "adapt", "Design saves, checkpoints, scene transitions and asset layout for " + target.artifact),
        PortAction("compatibility", "verify", "Define emulator or hardware validation; never bundle proprietary BIOS, firmware, keys or commercial ROMs"),
    ]
    if expanding and mode in (PortMode.ENHANCED, PortMode.CROSS_HYBRID):
        stages.extend((
            PortAction("visual_upgrade", "expand", "Increase detail, animation layers, parallax and lighting while preserving authored retro style"),
            PortAction("simulation_upgrade", "expand", "Improve physics, NPC behavior, camera options and level density without altering identity invariants"),
            PortAction("sound_upgrade", "expand", "Add spatial mixing, dynamic arrangements and optional classic-audio mode"),
            PortAction("usability_upgrade", "expand", "Add controller remapping, accessibility, save conveniences and configurable modern display modes"),
        ))
    elif reducing or mode is PortMode.REVERSE_CONSTRAINED:
        stages.extend((
            PortAction("visual_demotion", "constrain", "Retarget artwork to authentic tiles, palettes, sprites, vector or LCD rules"),
            PortAction("gameplay_demotion", "constrain", "Fit world sizes, animation and AI updates to deterministic hardware budgets"),
            PortAction("sound_demotion", "constrain", "Arrange audio for channel limits and avoid unsustainable runtime mixing"),
        ))
    elif mode is PortMode.ENHANCED:
        stages.append(PortAction("period_upgrade", "refine", "Use era-faithful polish only; do not promise capabilities the target lacks"))
    if hybrid:
        stages.extend((
            PortAction("hybrid_design", "compose", "Merge original mechanics and aesthetics into a newly authored, non-confusing identity"),
            PortAction("hybrid_clearance", "review", "Independently review both source licenses, marks, expressive similarity and attribution"),
        ))
    return tuple(stages)


_RELEASE_GATES = (
    "independent_rights_and_trademark_clearance",
    "asset_and_code_provenance_review",
    "target_sdk_and_toolchain_qualification",
    "real_hardware_or_representative_emulator_execution",
    "no_proprietary_firmware_or_protected_key_dependencies",
    "native_binary_build_and_install_receipt",
    "input_audio_video_timing_and_save_validation",
    "regression_replay_and_release_signoff",
)


def compile_port(request: PortRequest, registry: PlatformRegistry | None = None) -> PortBlueprint:
    """Compile a target-aware work plan. A blueprint does not produce a binary."""
    if not isinstance(request, PortRequest):
        raise PortPlanningError("expected PortRequest")
    registry = default_registry() if registry is None else registry
    if not isinstance(registry, PlatformRegistry):
        raise PortPlanningError("registry must be a validated PlatformRegistry")
    try:
        target = registry.get(request.target_platform_id)
        source_profiles = tuple(registry.get(s.platform_id) for s in request.sources)
    except PlatformRegistryError as exc:
        raise PortPlanningError("unknown platform in port plan") from exc
    creative = tuple(dict.fromkeys(term for s in request.sources for term in s.creative_identity))
    steps = _actions(target, source_profiles, request.mode)
    probes = (
        "original_mechanics_intact", "target_display_legible", "input_parity",
        "sound_originality_and_channel_budget", "save_and_restart",
        "deterministic_replay_on_target", "performance_frame_pacing",
        "rights_and_attribution_rechecked",
    )
    payload: dict[str, object] = {
        "schema_version": 1,
        "sources": [
            {"project_id": s.project_id, "platform_id": s.platform_id,
             "rights_basis": s.rights_basis, "evidence_sha256": s.evidence_sha256,
             "creative_identity": list(s.creative_identity)}
            for s in request.sources
        ],
        "target_platform_id": target.id,
        "target_preset": target.preset,
        "mode": request.mode.value,
        "design_intent": list(creative),
        "target_constraints": list(target.constraints),
        "actions": [{"phase": a.phase, "disposition": a.disposition, "work": a.work} for a in steps],
        "acceptance_probes": list(probes),
        "pending_release_gates": list(_RELEASE_GATES),
        "planning_status": "design_only_toolchain_unverified",
    }
    return PortBlueprint(
        schema_version=1, source_platform_ids=tuple(s.platform_id for s in request.sources),
        target_platform_id=target.id, mode=request.mode.value, design_intent=creative,
        target_constraints=target.constraints, actions=steps, acceptance_probes=probes,
        pending_release_gates=_RELEASE_GATES, planning_status="design_only_toolchain_unverified",
        digest=_deterministic_digest(payload),
    )


def compile_port_route(
    source: HomebrewSource, destinations: tuple[str, ...], *,
    mode: PortMode = PortMode.FAITHFUL, registry: PlatformRegistry | None = None,
) -> tuple[PortBlueprint, ...]:
    """Plan directed hops: e.g. WonderSwan -> Windows -> handheld; not a build."""
    registry = default_registry() if registry is None else registry
    if (
        not isinstance(source, HomebrewSource)
        or not isinstance(destinations, tuple)
        or not 1 <= len(destinations) <= 5
        or mode is PortMode.CROSS_HYBRID
    ):
        raise PortPlanningError("route needs one homebrew source, 1-5 destinations and a non-hybrid mode")
    if len(set((source.platform_id, *destinations))) != len(destinations) + 1:
        raise PortPlanningError("cyclic or repeated destination in port route")
    # The chain is conceptual: intermediate binary output is never invented.
    plans = []
    for platform_id in destinations:
        plans.append(compile_port(PortRequest((source,), platform_id, mode), registry))
    return tuple(plans)
