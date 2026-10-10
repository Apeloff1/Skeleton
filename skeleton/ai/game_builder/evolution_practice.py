"""Offline game-evolution practice: produce playable deterministic original prototypes.

This is a *real engine-neutral gameplay demonstration* with a reproducible
winning trace for each selected stage. It does NOT produce a native Game Boy,
arcade or PlayStation binary; hardware exporters must implement stage adapters.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from .evolution_archive import EvolutionCampaign, EvolutionStage, GameEvolutionError
from .platform_registry import default_registry
from .playable_simulation import GameReplay, demonstrate_solvable
from .playable_world import (
    GameBuildIntent, PlayableWorld, PlayableWorldError, generate_playable_world,
)

MAX_PRACTICE_STAGES = 24


@dataclass(frozen=True, slots=True)
class EvolutionPractice:
    stage_number: int
    intended_platform_id: str
    original_world_id: str
    game_world: PlayableWorld
    winning_replay: GameReplay
    design_signal_goals: tuple[str, ...]
    hardware_profile: str
    target_adapter_state: str = "concept_prototype_not_native"
    native_binary_built: bool = False

    def __post_init__(self) -> None:
        if self.winning_replay.world_digest != self.game_world.digest:
            raise GameEvolutionError("winning proof belongs to another generated game")
        if self.winning_replay.final_state.status != "won":
            raise GameEvolutionError("cannot accept unsolved evolution game")


@dataclass(frozen=True, slots=True)
class EvolutionPracticePack:
    campaign_project_id: str
    source_world_digest: str
    demos: tuple[EvolutionPractice, ...]
    archive_gameplay_status: str = "engine_neutral_playable_with_replay"
    shipped_console_binaries: int = 0

    def status(self) -> dict[str, object]:
        return {
            "original_project": self.campaign_project_id,
            "gameplay_worlds_generated": len(self.demos),
            "successful_deterministic_replays": sum(
                p.winning_replay.final_state.status == "won" for p in self.demos
            ),
            "console_roms_built": self.shipped_console_binaries,
            "needs_hardware_specific_native_compiler": True,
            "source_world_digest": self.source_world_digest,
        }


def _intention_for_stage(
    original: GameBuildIntent, stage: EvolutionStage, index: int,
) -> GameBuildIntent:
    registry = default_registry()
    target = registry.get(stage.to_platform)
    # Deterministic monotone budget envelopes: small historic designs teach
    # constrained gameplay; newer hardware unlocks spatial scope/interaction.
    # They are pedagogical envelopes, NOT accurate RAM, VRAM or clock claims.
    tier = target.tier
    dimensions = (9, 11, 13, 17, 21)
    width = min(original.width, dimensions[tier])
    height = min(original.height, dimensions[tier])
    if width % 2 == 0:
        width -= 1
    if height % 2 == 0:
        height -= 1
    levels = min(original.levels, 1 + min(tier, 3))
    collectibles = min(original.collectibles_per_level, 1 + min(tier, 3))
    hazards = min(original.hazards_per_level, 1 + tier)
    salt = (
        str(original.seed) + ":" + stage.to_platform + ":" + str(index)
        + ":" + str(stage.source_year) + ":" + str(stage.target_year)
    )
    seed = int.from_bytes(sha256(salt.encode()).digest()[:8], "big") & ((1 << 63) - 1)
    return GameBuildIntent(
        project_id=original.project_id,
        title=original.title,
        subtitle=original.subtitle,
        seed=seed,
        width=max(9, width),
        height=max(9, height),
        levels=levels,
        collectibles_per_level=max(1, collectibles),
        hazards_per_level=hazards,
        theme=original.theme,
        starting_health=original.starting_health,
    )


def practice_evolution_games(
    original_world: PlayableWorld, campaign: EvolutionCampaign, *,
    authorized: bool, maximum_stages: int = MAX_PRACTICE_STAGES,
) -> EvolutionPracticePack:
    if type(authorized) is not bool or not authorized:
        raise PermissionError("original game evolution requires authorization")
    if not isinstance(original_world, PlayableWorld) or not isinstance(campaign, EvolutionCampaign):
        raise GameEvolutionError("typed original world and campaign required")
    if original_world.intent.project_id != campaign.original_project_id:
        raise GameEvolutionError("campaign project differs from world project")
    if type(maximum_stages) is not int or not 1 <= maximum_stages <= MAX_PRACTICE_STAGES:
        raise GameEvolutionError("practice workload must be bounded")
    if not campaign.stages or len(campaign.stages) > maximum_stages:
        raise GameEvolutionError("invalid or oversized campaign for practice run")
    first = campaign.stages[0]
    if first.stage_number != 1 or not first.from_platform:
        raise GameEvolutionError("noncanonical campaign stage order")
    games: list[EvolutionPractice] = []
    previous_target = first.from_platform
    for i, stage in enumerate(campaign.stages, start=1):
        if (
            stage.stage_number != i or stage.from_platform != previous_target
            or stage.adaptation.target_platform_id != stage.to_platform
            or stage.retained_identity != first.retained_identity
            or stage.native_export_verified
        ):
            raise GameEvolutionError("untrusted or inconsistent evolution path")
        target = default_registry().get(stage.to_platform)
        intent = _intention_for_stage(original_world.intent, stage, i)
        try:
            game = generate_playable_world(intent, authorized=True)
            proof = demonstrate_solvable(game, authorized=True)
        except PlayableWorldError as exc:
            raise GameEvolutionError("failed to construct evolution practice world") from exc
        if proof.world_digest != game.digest or proof.final_state.status != "won":
            raise GameEvolutionError("evolution lesson is not reproducibly solvable")
        games.append(EvolutionPractice(
            stage_number=i,
            intended_platform_id=target.id,
            original_world_id=original_world.digest,
            game_world=game, winning_replay=proof,
            design_signal_goals=stage.unlocked_design_signals,
            hardware_profile=target.preset,
        ))
        previous_target = stage.to_platform
    return EvolutionPracticePack(campaign.original_project_id, original_world.digest, tuple(games))
