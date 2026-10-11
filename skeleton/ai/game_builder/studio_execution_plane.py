"""Executable, replay-audited local tool plane for original game creation.

This is the missing bridge between Jeeves' typed planning and Dragon's actual
game-building actions. No model is granted a shell, raw filesystem, network,
publisher credentials or arbitrary Python import. The only executable
capabilities are explicit, typed local handlers backed by existing canonical
game builders. Research/external tool IDs fail closed until separately wired.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence, Mapping

from .contracts import canonical_digest
from .tiled_map_import import TiledConversion, import_tiled_levels
from .living_story_runtime import (
    StoryIntent, StoryWorld, StoryReplay, original_story_world, demonstrate_story,
)
from .living_story_export import StoryPackage, render_story_package
from .living_story_mirror import StoryMirrorReport, review_living_story
from .companion_curriculum import (
    PracticeInsight, measure_original_practice, validate_practice_cohort,
)
from .dual_runtime_export import (
    DualRuntimePackage, export_dual_runtime_package, render_dual_runtime_package,
)
from .mirror_room_runtime import MirrorReport, review_playable_project
from .playable_compiler import (
    CompiledPlayableProject, compile_authored_game, compile_original_game,
)
from .playable_export import PlayableHTML
from .playable_simulation import GameReplay, demonstrate_solvable, verify_replay
from .playable_world import GameBuildIntent, PlayableWorld, generate_playable_world
from .studio_tool_fabric import Actor, Phase, ToolFabric, ToolPlan, ToolRequest


class ExecutionPlaneError(ValueError):
    """A proposed action is not executable under the verified local authority."""


# Deliberately small and auditable. A tool catalog entry never becomes a
# process-launch adapter just because an agent asks to invoke it.
EXECUTABLE_TOOLS = frozenset({
    "world.generate", "world.authored", "world.tiled", "game.simulate", "game.browser",
    "game.godot", "game.editor", "mirror.fuzz", "release.assess",
    "story.generate", "story.simulate", "story.native", "story.mirror",
    "package.source", "companion.practice",
})
MAX_EXECUTION_STEPS = 32


@dataclass(frozen=True, slots=True)
class ExecutedToolReceipt:
    index: int
    tool_id: str
    actor: Actor
    input_digest: str
    output_digest: str
    tool_spec_digest: str
    predecessor_digest: str | None
    evidence_digest: str
    status: str

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_payload())

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": "skeleton.game_builder.tool_execution_receipt.v1",
            "index": self.index,
            "tool_id": self.tool_id,
            "actor": self.actor.value,
            "input_digest": self.input_digest,
            "output_digest": self.output_digest,
            "tool_spec_digest": self.tool_spec_digest,
            "predecessor_digest": self.predecessor_digest,
            "evidence_digest": self.evidence_digest,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class ExecutionOutcome:
    intent_digest: str
    plan_digest: str
    receipts: tuple[ExecutedToolReceipt, ...]
    world: PlayableWorld | None
    project: CompiledPlayableProject | None
    package: DualRuntimePackage | None
    mirror: MirrorReport | None
    practice_packages: tuple[DualRuntimePackage, ...]
    practice_insights: tuple[PracticeInsight, ...]
    practice_mirror_reports: tuple[MirrorReport, ...]
    tiled_conversion: TiledConversion | None
    story_world: StoryWorld | None
    story_replay: StoryReplay | None
    story_package: StoryPackage | None
    story_mirror: StoryMirrorReport | None
    exported_path: Path | None

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_payload())

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": "skeleton.game_builder.tool_execution_outcome.v1",
            "intent_digest": self.intent_digest,
            "plan_digest": self.plan_digest,
            "receipts": [r.to_payload() for r in self.receipts],
            "world_digest": self.world.digest if self.world else None,
            "proof_digest": self.project.proof.digest if self.project else None,
            "package_manifest_digest": (
                self.package.manifest["manifest_digest"] if self.package else None
            ),
            "mirror_digest": self.mirror.digest if self.mirror else None,
            "practice_manifest_digests": [
                item.manifest["manifest_digest"] for item in self.practice_packages
            ],
            "practice_insight_digests": [item.digest for item in self.practice_insights],
            "practice_mirror_digests": [item.digest for item in self.practice_mirror_reports],
            "tiled_import_digest": (
                self.tiled_conversion.digest if self.tiled_conversion else None
            ),
            "living_story_world_digest": self.story_world.digest if self.story_world else None,
            "living_story_proof_digest": self.story_replay.digest if self.story_replay else None,
            "living_story_package_digest": self.story_package.digest if self.story_package else None,
            "living_story_mirror_digest": self.story_mirror.digest if self.story_mirror else None,
            "exported": self.exported_path is not None,
            "external_code_executed": False,
            "trained_model": False,
            "publication_approved": False,
        }


def execute_local_tool_plan(
    intent: GameBuildIntent,
    plan: ToolPlan,
    *,
    authorized: bool,
    fabric: ToolFabric | None = None,
    authored_levels: Sequence[object] | None = None,
    tiled_sources: Sequence[str | Path] | None = None,
    tiled_gid_palette: Mapping[int, str] | None = None,
    human_reviewed: bool = False,
    destination: Path | None = None,
    mirror_attempts: int = 128,
    companion_games: int = 2,
    story_intent: StoryIntent | None = None,
    story_ending: str = "stewardship",
) -> ExecutionOutcome:
    """Execute authorized plan in order, not arbitrary agent-supplied Python.

    The entire tool plan is verified before the first side effect; a *single*
    anchored world identity ties all derived artifacts and receipts together.
    Package.source has an additional explicit destination+write permission
    gate; it is never implicitly triggered by package compilation.
    """
    if not authorized:
        raise PermissionError("local game tool execution requires operator authorization")
    if not isinstance(intent, GameBuildIntent) or not isinstance(plan, ToolPlan):
        raise ExecutionPlaneError("typed original intent and pre-approved tool plan required")
    if type(mirror_attempts) is not int or not 64 <= mirror_attempts <= 512:
        raise ExecutionPlaneError("mirror-room execution budget must be 64 to 512")
    if type(companion_games) is not int or not 0 <= companion_games <= 8:
        raise ExecutionPlaneError("companion batch must be bounded to 0 to 8 playable games")
    if story_intent is not None and not isinstance(story_intent, StoryIntent):
        raise ExecutionPlaneError("typed original narrative intent required")
    if story_ending not in {"stewardship", "discovery", "independence"}:
        raise ExecutionPlaneError("narrative ending must be an original supported path")
    if fabric is None:
        fabric = ToolFabric()
    if not isinstance(fabric, ToolFabric):
        raise ExecutionPlaneError("trusted typed tool fabric required")
    anchored = canonical_digest(intent.to_payload())
    if not plan.requests or len(plan.requests) > MAX_EXECUTION_STEPS:
        raise ExecutionPlaneError("execution plan must contain 1 to 32 actions")
    # Recompute authority against the live registry, not simply the supplied
    # serialized ToolPlan/ToolSpec output or an assistant's claimed status.
    try:
        checked = fabric.plan(
            plan.requests, authorized=True,
            allow_filesystem_write=plan.write_authorized,
            max_resource_units=500,
        )
    except (ValueError, PermissionError) as exc:
        raise ExecutionPlaneError("tool plan failed fresh authority check") from exc
    if checked.external_blocked:
        raise ExecutionPlaneError("tool plan blocked or filesystem write grant missing")
    if checked.digest != plan.digest or checked.tool_digests != plan.tool_digests:
        raise ExecutionPlaneError("tool grant changed, is blocked or was forged")
    if any(
        not isinstance(row, ToolRequest) or row.input_digest != anchored
        or row.tool_id not in EXECUTABLE_TOOLS
        for row in plan.requests
    ):
        raise ExecutionPlaneError("local executor refuses unanchored or unsupported actions")
    ids = [row.tool_id for row in plan.requests]
    if len(ids) != len(set(ids)):
        raise ExecutionPlaneError("plan cannot execute a tool more than once per run")
    # Preflight dependency ordering, avoiding partial filesystem work before
    # a later step fails. CPU/resource budgets were checked above.
    seen: set[str] = set()
    for name in ids:
        deps = {
            "world.generate": (),
            "world.authored": (),
            "world.tiled": (),
            "game.simulate": ("world.generate", "world.authored", "world.tiled"),
            "game.browser": ("world.generate", "world.authored", "world.tiled"),
            "game.editor": ("world.generate", "world.authored", "world.tiled"),
            "game.godot": ("game.browser", "world.authored", "world.tiled"),
            "mirror.fuzz": ("game.godot",),
            "release.assess": ("mirror.fuzz",),
            "package.source": ("mirror.fuzz",),
            "companion.practice": (),
            "story.generate": (),
            "story.simulate": ("story.generate",),
            "story.native": ("story.simulate",),
            "story.mirror": ("story.native",),
        }[name]
        if deps and not any(dep in seen for dep in deps):
            raise ExecutionPlaneError(f"{name} lacks prior prerequisite {deps}")
        if name.startswith("world.") and any(x.startswith("world.") for x in seen):
            raise ExecutionPlaneError("one original world source per execution")
        seen.add(name)
    story_tools = tuple(x for x in ids if x.startswith("story."))
    if story_tools:
        if story_intent is None or story_tools != (
            "story.generate", "story.simulate", "story.native", "story.mirror",
        ):
            raise ExecutionPlaneError("story execution requires all four ordered capabilities and intent")
    elif story_intent is not None:
        raise ExecutionPlaneError("unplanned living-world engine work is not authorized")
    writes = any(row.tool_id == "package.source" for row in plan.requests)
    if writes and (not plan.write_authorized or not isinstance(destination, Path)):
        raise ExecutionPlaneError("package export requires explicit write grant and destination")
    if not writes and destination is not None:
        raise ExecutionPlaneError("destination supplied without a package-source operation")
    authored_mode = "world.authored" in ids
    tiled_mode = "world.tiled" in ids
    if authored_mode:
        if authored_levels is None or human_reviewed is not True or tiled_sources is not None:
            raise ExecutionPlaneError("human-reviewed original authored geometry required")
    elif tiled_mode:
        if tiled_sources is None or authored_levels is not None or human_reviewed is not True:
            raise ExecutionPlaneError("reviewed local Tiled map files required for world.tiled")
    elif authored_levels is not None or tiled_sources is not None or human_reviewed:
        raise ExecutionPlaneError("authored input provided without an authorized authored operation")

    world: PlayableWorld | None = None
    project: CompiledPlayableProject | None = None
    package: DualRuntimePackage | None = None
    mirror: MirrorReport | None = None
    practice: list[DualRuntimePackage] = []
    practice_insights: list[PracticeInsight] = []
    practice_mirrors: list[MirrorReport] = []
    exported: Path | None = None
    tiled_conversion: TiledConversion | None = None
    narrative: StoryWorld | None = None
    narrative_proof: StoryReplay | None = None
    narrative_package: StoryPackage | None = None
    narrative_mirror: StoryMirrorReport | None = None
    receipts: list[ExecutedToolReceipt] = []
    consumed = set()
    for index, row in enumerate(plan.requests):
        # A repeat can hide accidental double writes or inflated progress. For
        # replay, use a new plan instead of silently charging a second run.
        if row.tool_id in consumed:
            raise ExecutionPlaneError("repeated tool call not permitted within one plan")
        consumed.add(row.tool_id)
        tool = next((t for t in fabric.discover(actor=row.actor, phase=row.phase)
                     if t.tool_id == row.tool_id), None)
        if tool is None:
            raise ExecutionPlaneError("tool disappeared before execution")
        before = (package.manifest["manifest_digest"] if package else
                  project.proof.digest if project else world.digest if world else anchored)
        if row.tool_id == "story.generate":
            narrative = original_story_world(story_intent, authorized=True)
            artifact_digest = narrative.digest
        elif row.tool_id == "story.simulate":
            if narrative is None:
                raise ExecutionPlaneError("story simulation needs an original narrative world")
            narrative_proof = demonstrate_story(
                narrative, authorized=True, ending=story_ending,
            )
            artifact_digest = narrative_proof.digest
        elif row.tool_id == "story.native":
            if narrative is None or narrative_proof is None:
                raise ExecutionPlaneError("story export requires real winning choices")
            narrative_package = render_story_package(
                narrative, narrative_proof, authorized=True,
            )
            artifact_digest = narrative_package.digest
        elif row.tool_id == "story.mirror":
            if narrative is None or narrative_proof is None or narrative_package is None:
                raise ExecutionPlaneError("story mirror requires compiled source and actual proof")
            narrative_mirror = review_living_story(
                narrative, narrative_proof, narrative_package,
                authorized=True, attempts=128,
            )
            if not narrative_mirror.passed:
                raise ExecutionPlaneError("narrative mirror room refused the original game")
            artifact_digest = narrative_mirror.digest
        elif row.tool_id == "world.generate":
            if world is not None or project is not None:
                raise ExecutionPlaneError("original world already exists")
            world = generate_playable_world(intent, authorized=True)
            artifact_digest = world.digest
        elif row.tool_id == "world.authored":
            if world is not None or project is not None:
                raise ExecutionPlaneError("authored world conflicts with generated world")
            project = compile_authored_game(
                intent, authored_levels, human_reviewed=True, authorized=True,
            )
            world = project.world
            artifact_digest = world.digest
        elif row.tool_id == "world.tiled":
            if world is not None or project is not None:
                raise ExecutionPlaneError("Tiled import conflicts with previous original world")
            conversion = import_tiled_levels(
                intent, tiled_sources, human_reviewed=True,
                authorized=True, gid_palette=tiled_gid_palette,
            )
            tiled_conversion = conversion
            project = compile_authored_game(
                intent, [list(rows) for rows in conversion.levels],
                human_reviewed=True, authorized=True,
            )
            world = project.world
            if world.digest != conversion.world_digest:
                raise ExecutionPlaneError("Tiled conversion and canonical authored world diverged")
            artifact_digest = conversion.digest
        elif row.tool_id == "game.simulate":
            if world is None:
                raise ExecutionPlaneError("simulation needs a previously constructed world")
            proof: GameReplay = demonstrate_solvable(world, authorized=True)
            if proof.final_state.status != "won":
                raise ExecutionPlaneError("world has no winning replay")
            artifact_digest = proof.digest
        elif row.tool_id == "game.browser":
            if world is None:
                raise ExecutionPlaneError("browser rendering needs a world")
            if project is None:
                project = compile_original_game(intent, authorized=True)
                if project.world != world:
                    raise ExecutionPlaneError("renderer generated a different world")
            artifact_digest = project.playable.html_sha256
        elif row.tool_id == "game.godot":
            if project is None:
                raise ExecutionPlaneError("Godot source requires a verified browser project")
            package = render_dual_runtime_package(project, authorized=True)
            artifact_digest = str(package.manifest["manifest_digest"])
        elif row.tool_id == "game.editor":
            if world is None:
                raise ExecutionPlaneError("editor requires original world")
            from .tile_editor_export import render_tile_editor
            artifact_digest = render_tile_editor(world, authorized=True).source_sha256
        elif row.tool_id == "mirror.fuzz":
            if project is None or package is None:
                raise ExecutionPlaneError("mirror room requires real compiled browser+native project")
            mirror = review_playable_project(
                project, package, authorized=True, attempts=mirror_attempts,
            )
            if not mirror.passed:
                raise ExecutionPlaneError("mirror room rejected playable artifact")
            artifact_digest = mirror.digest
        elif row.tool_id == "companion.practice":
            from .companion_curriculum import plan_original_companion_intents
            variants = plan_original_companion_intents(intent, companion_games)
            theme_count = validate_practice_cohort(variants, parent=intent)
            for practice_intent in variants:
                practice_project = compile_original_game(practice_intent, authorized=True)
                practice_package = render_dual_runtime_package(practice_project, authorized=True)
                # Every stepping-stone title must survive attacks on its own
                # replay, identity, source and manifest before learning XP.
                inspection = review_playable_project(
                    practice_project, practice_package,
                    authorized=True, attempts=64,
                )
                if not inspection.passed:
                    raise ExecutionPlaneError("companion practice failed independent mirror room")
                practice.append(practice_package)
                practice_mirrors.append(inspection)
                practice_insights.append(measure_original_practice(
                    practice_project.world, practice_project.proof,
                    authorized=True, distinct_themes=theme_count,
                ))
            artifact_digest = canonical_digest({
                "practice_manifests": [
                    pkg.manifest["manifest_digest"] for pkg in practice
                ],
                "insights": [row.digest for row in practice_insights],
                "mirror_reports": [row.digest for row in practice_mirrors],
            })
        elif row.tool_id == "release.assess":
            if mirror is None or not mirror.passed:
                raise ExecutionPlaneError("release assessment must follow verified mirror room")
            artifact_digest = canonical_digest({
                "status": "release-blocked",
                "world_digest": world.digest,
                "mirror_digest": mirror.digest,
                "outstanding": (
                    "rights", "human_playtesting", "native_hardware",
                    "malware_scanning", "accessibility", "localization",
                    "code_signing", "platform_permission", "publisher_approval",
                ),
            })
        elif row.tool_id == "package.source":
            if package is None or mirror is None or not mirror.passed:
                raise ExecutionPlaneError("export requires a mirror-approved native+browser package")
            exported = export_dual_runtime_package(package, destination, authorized=True)
            artifact_digest = str(package.manifest["manifest_digest"])
        else:
            raise ExecutionPlaneError("tool has no local execution implementation")
        receipts.append(ExecutedToolReceipt(
            index, row.tool_id, row.actor, before, artifact_digest,
            tool.digest, receipts[-1].digest if receipts else None,
            canonical_digest({
                "anchored_intent": anchored,
                "tool": row.to_payload(),
                "result": artifact_digest,
            }),
            "executed",
        ))
    return ExecutionOutcome(
        anchored, plan.digest, tuple(receipts), world, project,
        package, mirror, tuple(practice), tuple(practice_insights),
        tuple(practice_mirrors), tiled_conversion,
        narrative, narrative_proof, narrative_package, narrative_mirror,
        exported,
    )


__all__ = [
    "ExecutionPlaneError", "ExecutedToolReceipt", "ExecutionOutcome",
    "EXECUTABLE_TOOLS", "execute_local_tool_plan",
]
