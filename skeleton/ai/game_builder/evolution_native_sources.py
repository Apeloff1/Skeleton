"""Turn historical *game-evolution practice worlds* into real native game sources.

The archive is not merely a design index: compatible exercises emit executable
source projects for genuine desktop machines and Game Boy DMG cartridges.
Every stage is tracked independently, including design-only and dimension-bound
stages. Native compilation, emulator execution and distribution are separate.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from .desktop_native_export import (
    NativeDesktopExportError, NativeDesktopSourceProject,
    compile_native_desktop, export_native_desktop_source,
)
from .evolution_archive import GameEvolutionError
from .evolution_practice import EvolutionPracticePack, MAX_PRACTICE_STAGES
from .game_boy_native_export import (
    GameBoySourceError, GameBoySourceProject,
    compile_native_game_boy, export_native_game_boy,
)
from .game_boy_color_native_export import (
    GameBoyColorSourceError, GameBoyColorSourceProject,
    compile_native_game_boy_color, export_native_game_boy_color,
)
from .nes_native_export import (
    NativeNESError, NativeNESSourceProject, compile_native_nes, export_native_nes,
)
from .c64_native_export import NativeC64Error, NativeC64SourceProject, compile_native_c64, export_native_c64
from .dos_native_export import NativeDOSError, NativeDOSSourceProject, compile_native_dos, export_native_dos
from .atari8_native_export import Atari8BitNativeError, Atari8BitSourceProject, compile_native_atari8, export_native_atari8
from .apple2_native_export import Apple2NativeError, Apple2SourceProject, compile_native_apple2, export_native_apple2
from .port_planner import HomebrewSource

_DESKTOP = frozenset({"windows_modern", "linux_desktop", "macos_modern"})
_HANDHELD = frozenset({"nintendo_game_boy", "nintendo_game_boy_color"})
_ALLOWED_EXPORTS = _DESKTOP | _HANDHELD
_STATUSES = frozenset({"native_source_ready", "budget_incompatible", "design_only"})


@dataclass(frozen=True, slots=True)
class EvolutionNativeStage:
    stage_number: int
    target_platform_id: str
    world_digest: str
    replay_digest: str
    source_kind: str | None
    source_digest: str | None
    status: str
    project: NativeDesktopSourceProject | GameBoySourceProject | NativeNESSourceProject | NativeC64SourceProject | NativeDOSSourceProject | Atari8BitSourceProject | GameBoyColorSourceProject | Apple2SourceProject | None

    def __post_init__(self):
        if self.status not in _STATUSES:
            raise GameEvolutionError("invalid evolution hardware stage disposition")
        if (self.project is None) != (self.status != "native_source_ready"):
            raise GameEvolutionError("native practice source disposition inconsistent")
        if self.project is not None and self.source_digest != self.project.content_digest:
            raise GameEvolutionError("source digest not bound to source project")
        if len(self.world_digest) != 64 or len(self.replay_digest) != 64:
            raise GameEvolutionError("missing evolution replay or world identity")

    def summary(self) -> dict[str, object]:
        return {
            "stage": self.stage_number,
            "platform": self.target_platform_id,
            "world_digest": self.world_digest,
            "replay_digest": self.replay_digest,
            "status": self.status,
            "source_kind": self.source_kind,
            "source_digest": self.source_digest,
            "native_binary_built": False,
            "emulator_or_hardware_played": False,
            "distribution_licensed": False,
        }


@dataclass(frozen=True, slots=True)
class EvolutionNativeSourcePack:
    project_id: str
    original_world_digest: str
    stages: tuple[EvolutionNativeStage, ...]
    source_rights_reference: str
    digest: str

    def summary(self) -> dict[str, object]:
        return {
            "schema": "skeleton.game_builder.evolution_native_sources.v1",
            "project": self.project_id,
            "source_rights_reference": self.source_rights_reference,
            "original_world_digest": self.original_world_digest,
            "native_source_stages": sum(row.project is not None for row in self.stages),
            "design_only_stages": sum(row.status == "design_only" for row in self.stages),
            "budget_incompatible_stages": sum(row.status == "budget_incompatible" for row in self.stages),
            "total_stages": len(self.stages),
            "compiled_binaries": 0,
            "hardware_verified": 0,
            "distribution_licensed": False,
            "digest": self.digest,
            "stages": [row.summary() for row in self.stages],
        }


def compile_evolution_native_sources(
    practice: EvolutionPracticePack, source: HomebrewSource, *, authorized: bool,
) -> EvolutionNativeSourcePack:
    """Compile real source games from each qualified original practice world.

    Non-native historical stages remain honest design-only rows; incompatible
    Game Boy grid dimensions are never cropped or falsely marked executable.
    """
    if type(authorized) is not bool or not authorized:
        raise PermissionError("evolution native source build requires authorization")
    if not isinstance(practice, EvolutionPracticePack) or not isinstance(source, HomebrewSource):
        raise GameEvolutionError("typed practice run and original rights source required")
    if practice.campaign_project_id != source.project_id:
        raise GameEvolutionError("source rights project does not match campaign")
    if not practice.demos or len(practice.demos) > MAX_PRACTICE_STAGES:
        raise GameEvolutionError("unbounded or empty evolution source campaign")
    if practice.shipped_console_binaries:
        raise GameEvolutionError("practice cannot self-certify historical binary builds")
    built: list[EvolutionNativeStage] = []
    for index, stage in enumerate(practice.demos, start=1):
        if stage.stage_number != index:
            raise GameEvolutionError("missing or reordered evolution stage")
        if stage.original_world_id != practice.source_world_digest:
            raise GameEvolutionError("stage originally derived from different world")
        if stage.game_world.intent.project_id != source.project_id:
            raise GameEvolutionError("stage game identity differs from rights source")
        if stage.winning_replay.world_digest != stage.game_world.digest:
            raise GameEvolutionError("stage replay no longer matches generated game")
        if stage.winning_replay.final_state.status != "won":
            raise GameEvolutionError("cannot export losing or incomplete practice game")
        if stage.native_binary_built or stage.target_adapter_state != "concept_prototype_not_native":
            raise GameEvolutionError("upstream practice has forged hardware build assertion")
        target = stage.intended_platform_id
        project: NativeDesktopSourceProject | GameBoySourceProject | NativeNESSourceProject | NativeC64SourceProject | NativeDOSSourceProject | Atari8BitSourceProject | GameBoyColorSourceProject | Apple2SourceProject | None = None
        status = "design_only"
        if target in _DESKTOP:
            try:
                project = compile_native_desktop(stage.game_world, source, target, authorized=True)
            except NativeDesktopExportError as exc:
                raise GameEvolutionError("desktop native compiler refused practice stage") from exc
        elif target == "nintendo_game_boy":
            try:
                project = compile_native_game_boy(stage.game_world, source, authorized=True)
            except GameBoySourceError as exc:
                if "exceeds DMG" not in str(exc):
                    raise GameEvolutionError("handheld compiler refused practice stage") from exc
                status = "budget_incompatible"
        elif target == "nintendo_game_boy_color":
            try:
                project = compile_native_game_boy_color(stage.game_world, source, authorized=True)
            except GameBoyColorSourceError as exc:
                if "gameplay engine" not in str(exc):
                    raise GameEvolutionError("CGB color compiler refused original stage") from exc
                status = "budget_incompatible"
        elif target == "nintendo_famicom":
            try:
                project = compile_native_nes(stage.game_world, source, authorized=True)
            except NativeNESError as exc:
                if "envelope exceeded" not in str(exc):
                    raise GameEvolutionError("NES compiler refused practice stage") from exc
                status = "budget_incompatible"
        elif target == "commodore_64":
            try:
                project = compile_native_c64(stage.game_world, source, authorized=True)
            except NativeC64Error as exc:
                if "screen envelope" not in str(exc):
                    raise GameEvolutionError("C64 compiler refused original practice stage") from exc
                status = "budget_incompatible"
        elif target == "dos_vga":
            try:
                project = compile_native_dos(stage.game_world, source, authorized=True)
            except NativeDOSError as exc:
                if "budget exceeded" not in str(exc):
                    raise GameEvolutionError("DOS real-mode compiler refused practice stage") from exc
                status = "budget_incompatible"
        elif target == "apple_ii":
            try:
                project = compile_native_apple2(stage.game_world, source, authorized=True)
            except Apple2NativeError as exc:
                if "budget exceeded" not in str(exc):
                    raise GameEvolutionError("Apple II compiler refused original stage") from exc
                status = "budget_incompatible"
        elif target == "atari_400_800":
            try:
                project = compile_native_atari8(stage.game_world, source, authorized=True)
            except Atari8BitNativeError as exc:
                if "budget exceeded" not in str(exc):
                    raise GameEvolutionError("Atari 8-bit compiler refused practice stage") from exc
                status = "budget_incompatible"
        if project is not None:
            status = "native_source_ready"
        built.append(EvolutionNativeStage(
            stage_number=index, target_platform_id=target,
            world_digest=stage.game_world.digest,
            replay_digest=stage.winning_replay.digest,
            source_kind=project.output_kind if isinstance(project, NativeDesktopSourceProject)
                else project.artifact_kind if project is not None else None,
            source_digest=project.content_digest if project is not None else None,
            status=status, project=project,
        ))
    seed = {
        "schema": "skeleton.game_builder.evolution_native_sources.v1",
        "project_id": source.project_id,
        "rights": source.evidence_sha256,
        "original_world": practice.source_world_digest,
        "stages": [s.summary() for s in built],
    }
    digest = sha256(json.dumps(seed, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return EvolutionNativeSourcePack(
        source.project_id, practice.source_world_digest,
        tuple(built), source.evidence_sha256, digest,
    )


def export_evolution_native_sources(
    pack: EvolutionNativeSourcePack, destination: str | Path, *, authorized: bool,
) -> Path:
    if type(authorized) is not bool or not authorized:
        raise PermissionError("evolution native export requires authorization")
    if not isinstance(pack, EvolutionNativeSourcePack):
        raise GameEvolutionError("typed evolution source pack required")
    root = Path(destination)
    if root.exists() or root.is_symlink():
        raise FileExistsError(str(root))
    # All native source games are already compiled in memory, with no shell.
    # Use a new root and deterministic stage directory names only.
    root.mkdir(parents=True, exist_ok=False)
    for stage in pack.stages:
        if stage.project is None:
            continue
        folder = root / f"stage-{stage.stage_number:02d}-{stage.target_platform_id}"
        if isinstance(stage.project, GameBoySourceProject):
            export_native_game_boy(stage.project, folder, authorized=True)
        elif isinstance(stage.project, GameBoyColorSourceProject):
            export_native_game_boy_color(stage.project, folder, authorized=True)
        elif isinstance(stage.project, NativeNESSourceProject):
            export_native_nes(stage.project, folder, authorized=True)
        elif isinstance(stage.project, NativeC64SourceProject):
            export_native_c64(stage.project, folder, authorized=True)
        elif isinstance(stage.project, NativeDOSSourceProject):
            export_native_dos(stage.project, folder, authorized=True)
        elif isinstance(stage.project, Apple2SourceProject):
            export_native_apple2(stage.project, folder, authorized=True)
        elif isinstance(stage.project, Atari8BitSourceProject):
            export_native_atari8(stage.project, folder, authorized=True)
        else:
            export_native_desktop_source(stage.project, folder, authorized=True)
    with (root / "evolution-native-manifest.json").open("x", encoding="utf-8", newline="\n") as output:
        json.dump(pack.summary(), output, sort_keys=True, indent=2)
        output.write("\n")
    return root
