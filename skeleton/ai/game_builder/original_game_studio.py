"""Real offline game studio: original -> stepping stone -> consumer candidate.

Jeeves plans and checks the steps; Dragon receives a bounded deterministic
execution envelope; companion practice creates *new original* games; mirror
room attacks the actual project. No AI provider, crawler, engine plugin or
external service is fabricated by this local implementation.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Mapping, Sequence

from .contracts import canonical_digest
from .living_story_runtime import StoryIntent
from .living_story_authoring import (
    AuthoredStory, derive_original_story_intent, read_story_blueprint,
)
from .living_story_export import StoryPackage
from .living_story_mirror import StoryMirrorReport
from .companion_curriculum import (
    PracticeInsight, measure_original_practice, validate_practice_cohort,
)
from .dual_runtime_export import (
    DualRuntimePackage, render_dual_runtime_package, export_dual_runtime_package,
)
from .mirror_room_runtime import MirrorReport, review_playable_project
from .playable_compiler import (
    CompiledPlayableProject, compile_original_game, compile_authored_game,
)
from .playable_world import GameBuildIntent
from .studio_tool_fabric import Actor, Phase, ToolFabric, ToolPlan, ToolRequest


class StudioError(ValueError):
    """Illegal studio handoff or release-assurance misrepresentation."""


def _stable_bytes(payload: object) -> bytes:
    return (json.dumps(payload, sort_keys=True, ensure_ascii=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


@dataclass(frozen=True, slots=True)
class StudioStage:
    name: str
    input_digest: str
    output_digest: str
    tool_plan_digest: str
    evidence_digest: str

    def to_payload(self) -> dict[str, object]:
        return {
            "stage": self.name, "input_digest": self.input_digest,
            "output_digest": self.output_digest,
            "tool_plan_digest": self.tool_plan_digest,
            "evidence_digest": self.evidence_digest,
        }


@dataclass(frozen=True, slots=True)
class ConsumerReview:
    original_source: bool
    canonical_proof: bool
    mirror_passed: bool
    rights_reviewed: bool
    human_playtested: bool
    platform_hardware_tested: bool
    accessibility_reviewed: bool
    localization_reviewed: bool
    malware_scan_passed: bool
    code_signed: bool
    platform_permission_verified: bool
    approved_for_publication: bool

    @property
    def blockers(self) -> tuple[str, ...]:
        return tuple(name for name in (
            "original_source", "canonical_proof", "mirror_passed",
            "rights_reviewed", "human_playtested", "platform_hardware_tested",
            "accessibility_reviewed", "localization_reviewed",
            "malware_scan_passed", "code_signed",
            "platform_permission_verified", "approved_for_publication",
        ) if not getattr(self, name))

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": "skeleton.game_builder.consumer_review.v1",
            "status": "ready-for-authorized-publication" if not self.blockers else "release-blocked",
            "evidence": {name: getattr(self, name) for name in (
                "original_source", "canonical_proof", "mirror_passed",
                "rights_reviewed", "human_playtested", "platform_hardware_tested",
                "accessibility_reviewed", "localization_reviewed",
                "malware_scan_passed", "code_signed",
                "platform_permission_verified", "approved_for_publication",
            )},
            "blockers": list(self.blockers),
            "not_a_legal_opinion": True,
        }


@dataclass(frozen=True, slots=True)
class CompanionPractice:
    seed: int
    intent_digest: str
    world_digest: str
    proof_digest: str
    winning_steps: int
    capability_xp: int
    insight_digest: str
    challenge_score: int
    mirror_report_digest: str
    mirror_attempts: int
    package_manifest_digest: str
    package_path: str

    def to_payload(self) -> dict[str, object]:
        return {
            "seed": self.seed,
            "intent_digest": self.intent_digest,
            "world_digest": self.world_digest,
            "proof_digest": self.proof_digest,
            "winning_steps": self.winning_steps,
            "verified_capability_xp": self.capability_xp,
            "machine_almanac_insight_digest": self.insight_digest,
            "measured_challenge_score": self.challenge_score,
            "mirror_report_digest": self.mirror_report_digest,
            "verified_mirror_attempts": self.mirror_attempts,
            "package_manifest_digest": self.package_manifest_digest,
            "package_path": self.package_path,
        }


@dataclass(frozen=True, slots=True)
class StudioRun:
    project: CompiledPlayableProject
    source: str
    stages: tuple[StudioStage, ...]
    tool_plan: ToolPlan
    mirror: MirrorReport
    consumer: ConsumerReview
    practice: tuple[CompanionPractice, ...]
    package: DualRuntimePackage
    narrative: StoryPackage | None = None
    narrative_mirror: StoryMirrorReport | None = None

    @property
    def digest(self) -> str:
        return canonical_digest({
            "schema": "skeleton.game_builder.studio_run.v1",
            "world_digest": self.project.world.digest,
            "source": self.source,
            "stage_digests": [canonical_digest(s.to_payload()) for s in self.stages],
            "tool_plan_digest": self.tool_plan.digest,
            "mirror_digest": self.mirror.digest,
            "consumer_digest": canonical_digest(self.consumer.to_payload()),
            "practice_worlds": [p.world_digest for p in self.practice],
            "package_digest": self.package.manifest["manifest_digest"],
            "living_world_digest": self.narrative.digest if self.narrative else None,
            "living_mirror_digest": self.narrative_mirror.digest if self.narrative_mirror else None,
        })


def _practice_intents(base: GameBuildIntent, count: int) -> tuple[GameBuildIntent, ...]:
    """Full mechanical/theme curriculum; never cloned RNG-only variants."""
    from .companion_curriculum import plan_original_companion_intents
    return plan_original_companion_intents(base, count)


def run_original_game_studio(
    intent: GameBuildIntent,
    *,
    authorized: bool,
    human_reviewed_tiles: tuple[object, ...] | list[object] | None = None,
    tiled_sources: Sequence[str | Path] | None = None,
    tiled_gid_palette: Mapping[int, str] | None = None,
    human_authored_approved: bool = False,
    reviewed_library: object | None = None,
    research_brief: object | None = None,
    rights_ledger: object | None = None,
    human_research_approved: bool = False,
    mirror_attempts: int = 128,
    companion_practice_games: int = 2,
    narrative_population: int = 0,
    narrative_regions: int = 7,
    narrative_mode: str = "postgame",
    narrative_quests: int = 2,
    narrative_arcs: int = 3,
    narrative_ending: str = "stewardship",
    narrative_blueprint: str | Path | None = None,
    narrative_human_reviewed: bool = False,
    fabric: ToolFabric | None = None,
) -> StudioRun:
    """Execute actual offline work, rather than recording imaginary AI activity.

    The companion can earn XP only from generated, executable, winning games.
    Built-in tool plans are evidence-linked; no registered external tool runs.
    """
    if not authorized:
        raise PermissionError("offline studio execution requires operator authorization")
    if not isinstance(intent, GameBuildIntent):
        raise StudioError("typed original game intent required")
    if type(companion_practice_games) is not int or not 0 <= companion_practice_games <= 8:
        raise StudioError("companion practice batch must be 0 to 8 playable games")
    if type(mirror_attempts) is not int or not 64 <= mirror_attempts <= 512:
        raise StudioError("adversarial mirror attempts must be 64 to 512")
    if type(narrative_population) is not int or (
        narrative_population != 0 and not 6 <= narrative_population <= 128
    ):
        raise StudioError("living-world NPC budget must be zero or 6 to 128")
    if narrative_population and (
        type(narrative_regions) is not int or not 4 <= narrative_regions <= 12
        or narrative_mode not in {"campaign", "postgame", "sandbox"}
        or type(narrative_arcs) is not int or not 3 <= narrative_arcs <= 24
        or type(narrative_quests) is not int or not 1 <= narrative_quests <= narrative_arcs
        or narrative_ending not in {"stewardship", "discovery", "independence"}
    ):
        raise StudioError("invalid living-world region, mode, quest or ending settings")
    if narrative_blueprint is not None and (
        not narrative_population or narrative_human_reviewed is not True
    ):
        raise StudioError("human-reviewed, enabled living-world source required for custom NPC authoring")
    if narrative_blueprint is None and narrative_human_reviewed:
        raise StudioError("author review requires an original living-world blueprint")
    story_intent: StoryIntent | None = None
    authored_story: AuthoredStory | None = None
    if narrative_population:
        story_intent = derive_original_story_intent(
            intent, population=narrative_population,
            regions=narrative_regions, mode=narrative_mode,
            quests=narrative_quests, arcs=narrative_arcs, authorized=True,
        )
    elif (narrative_regions, narrative_mode, narrative_quests,
          narrative_arcs, narrative_ending) != (
        7, "postgame", 2, 3, "stewardship"
    ):
        raise StudioError("living-world configuration needs enabled NPC population")
    if narrative_blueprint is not None:
        authored_story = read_story_blueprint(
            story_intent, narrative_blueprint,
            human_reviewed=True, authorized=True,
        )
    if human_reviewed_tiles is None and tiled_sources is None and human_authored_approved:
        raise StudioError("authored approval cannot be applied to generated levels")
    if human_reviewed_tiles is not None and tiled_sources is not None:
        raise StudioError("Tiled input and authored editor JSON are mutually exclusive")
    if tiled_gid_palette is not None and tiled_sources is None:
        raise StudioError("Tiled GID mapping requires Tiled geometry source")
    research_enabled = any(
        value is not None for value in (reviewed_library, research_brief, rights_ledger)
    ) or human_research_approved
    if research_enabled:
        if (reviewed_library is None or research_brief is None or rights_ledger is None
                or type(human_research_approved) is not bool
                or not human_research_approved):
            raise StudioError("research requires reviewed library, brief, rights and human approval")
        if human_reviewed_tiles is not None or tiled_sources is not None:
            raise StudioError("authored editor and Tiled games need independent rights handoff")
        if story_intent is not None:
            raise StudioError("living-world research clearance needs an independent story rights lane")
    if (human_reviewed_tiles is not None or tiled_sources is not None) and not human_authored_approved:
        raise StudioError("manually authored geometry requires human review")
    if fabric is None:
        fabric = ToolFabric()
    if not isinstance(fabric, ToolFabric):
        raise StudioError("typed game-tool fabric required")
    source = ("original-tiled" if tiled_sources is not None
              else "original-authored" if human_reviewed_tiles is not None
              else "original-research-referenced" if research_enabled
              else "original-generated")
    work = [
        (Actor.JEEVES, Phase.ORIGINAL,
         "world.tiled" if tiled_sources is not None else
         "world.authored" if human_reviewed_tiles is not None else "world.generate"),
        (Actor.DRAGON, Phase.STEPPING_STONE, "game.simulate"),
        (Actor.DRAGON, Phase.STEPPING_STONE, "game.browser"),
        (Actor.DRAGON, Phase.STEPPING_STONE, "game.godot"),
        (Actor.COMPANION, Phase.STEPPING_STONE, "companion.practice"),
        (Actor.MIRROR, Phase.REVIEW, "mirror.fuzz"),
        (Actor.JEEVES, Phase.CONSUMER, "release.assess"),
        (Actor.JEEVES, Phase.CONSUMER, "package.source"),
    ]
    if story_intent is not None:
        work[4:4] = [
            (Actor.DRAGON, Phase.ORIGINAL, "story.generate"),
            (Actor.DRAGON, Phase.STEPPING_STONE, "story.simulate"),
            (Actor.DRAGON, Phase.STEPPING_STONE, "story.native"),
            (Actor.MIRROR, Phase.REVIEW, "story.mirror"),
        ]
    if research_enabled:
        work[:0] = [
            (Actor.JEEVES, Phase.RESEARCH, "knowledge.search"),
            (Actor.JEEVES, Phase.RESEARCH, "rights.check"),
        ]
    requests = tuple(ToolRequest(actor, phase, tool,
                                 canonical_digest(intent.to_payload()),
                                 "Build and inspect independently reproducible original game")
                     for actor, phase, tool in work)
    plan = fabric.plan(
        requests, authorized=True, allow_filesystem_write=True,
    )
    if plan.external_blocked:
        raise StudioError("studio cannot execute blocked or externally unverified tools")
    execution_audit: dict[str, object]
    native_practice_packages: tuple[DualRuntimePackage, ...] | None = None
    native_insights: tuple[PracticeInsight, ...] | None = None
    native_mirrors: tuple[MirrorReport, ...] | None = None
    tiled_import_receipt: dict[str, object] | None = None
    living_package: StoryPackage | None = None
    living_mirror: StoryMirrorReport | None = None
    if research_enabled:
        from .playable_compiler import compile_game_from_reviewed_research
        # The canonical research bridge independently validates the library,
        # approved brief and RightsLedger. This is not a generic tool adapter.
        project = compile_game_from_reviewed_research(
            reviewed_library, research_brief, rights_ledger, intent,
            human_approved=True, authorized=True,
        )
        package = render_dual_runtime_package(project, authorized=True)
        mirror = review_playable_project(
            project, package, authorized=True, attempts=mirror_attempts,
        )
        execution_audit = {
            "schema": "skeleton.game_builder.studio_execution_binding.v1",
            "mode": "canonical-research-rights-bridge",
            "reviewed_game_receipt_digest": project.receipt()["receipt_digest"],
            "mirror_digest": mirror.digest,
            "delegated_external_tools": False,
            "generic_tool_plane_executed": False,
        }
    else:
        from .studio_execution_plane import execute_local_tool_plan
        # All local game-construction steps (except the final atomic write)
        # are now *really executed* by Jeeves/Dragon/Companion/Mirror's
        # freshly authorized tool plan, with a per-operation receipt chain.
        local_plan = fabric.plan(
            requests[:-1], authorized=True, allow_filesystem_write=False,
        )
        executed = execute_local_tool_plan(
            intent, local_plan, authorized=True, fabric=fabric,
            authored_levels=human_reviewed_tiles,
            tiled_sources=tiled_sources,
            tiled_gid_palette=tiled_gid_palette,
            human_reviewed=human_authored_approved,
            mirror_attempts=mirror_attempts,
            companion_games=companion_practice_games,
            story_intent=story_intent,
            authored_story_world=(authored_story.world if authored_story is not None else None),
            story_ending=narrative_ending,
        )
        if executed.project is None or executed.package is None or executed.mirror is None:
            raise StudioError("tool plane failed to deliver a proved game")
        project, package, mirror = executed.project, executed.package, executed.mirror
        native_practice_packages = executed.practice_packages
        native_insights = executed.practice_insights
        native_mirrors = executed.practice_mirror_reports
        living_package = executed.story_package
        living_mirror = executed.story_mirror
        if authored_story is not None and (
            executed.story_world is None or
            executed.story_world.digest != authored_story.world.digest
        ):
            raise StudioError("custom human-authored living-world source differed from executed world")
        if story_intent is not None and (
            living_package is None or living_mirror is None or not living_mirror.passed
            or living_mirror.package_digest != living_package.digest
        ):
            raise StudioError("living-world RPG failed actual mirror-room production gates")
        if executed.tiled_conversion is not None:
            if executed.tiled_conversion.world_digest != project.world.digest:
                raise StudioError("Tiled and original game geometry evidence diverged")
            tiled_import_receipt = executed.tiled_conversion.receipt()
        execution_audit = executed.to_payload()
    if not mirror.passed:
        raise StudioError("adversarial game mirror room found a failure")
    practice: list[CompanionPractice] = []
    practice_files: dict[str, bytes] = {}
    practice_intents = _practice_intents(intent, companion_practice_games)
    diversity_count = validate_practice_cohort(practice_intents, parent=intent)
    almanac_insights: list[PracticeInsight] = []
    companion_mirrors: list[MirrorReport] = []
    if native_mirrors is not None and len(native_mirrors) != len(practice_intents):
        raise StudioError("companion mirror coverage does not match practice titles")
    if native_insights is not None and len(native_insights) != len(practice_intents):
        raise StudioError("tool execution produced an unexpected insight count")
    if native_practice_packages is not None and len(native_practice_packages) != len(practice_intents):
        raise StudioError("tool execution produced an unexpected practice game count")
    for index, sample in enumerate(practice_intents, 1):
        if native_practice_packages is None:
            candidate = compile_original_game(sample, authorized=True)
            practice_package = render_dual_runtime_package(candidate, authorized=True)
            winning_steps = candidate.proof.final_state.steps
            insight = measure_original_practice(
                candidate.world, candidate.proof, authorized=True,
                distinct_themes=diversity_count,
            )
            individual_mirror = review_playable_project(
                candidate, practice_package, authorized=True, attempts=64,
            )
        else:
            practice_package = native_practice_packages[index - 1]
            insight = native_insights[index - 1]
            individual_mirror = native_mirrors[index - 1]
            proof_data = json.loads(
                practice_package.files["proof/verified_solution.json"].decode("utf-8")
            )
            winning_steps = len(proof_data["actions"])
        if (insight.world_digest != practice_package.manifest["world_digest"]
                or insight.proof_digest != practice_package.manifest["proof_digest"]
                or insight.safe_solution_turns != winning_steps
                or insight.intent_digest != canonical_digest(sample.to_payload())):
            raise StudioError("companion almanac evidence conflicts with executable practice game")
        if (not individual_mirror.passed
                or len(individual_mirror.probes) < 64
                or individual_mirror.world_digest != practice_package.manifest["world_digest"]
                or individual_mirror.proof_digest != practice_package.manifest["proof_digest"]
                or individual_mirror.package_digest != practice_package.manifest["manifest_digest"]):
            raise StudioError("companion practice failed its own independent mirror campaign")
        companion_mirrors.append(individual_mirror)
        almanac_insights.append(insight)
        if practice_package.manifest["project_id"] != sample.project_id:
            raise StudioError("companion practice package identity mismatch")
        if (practice_package.manifest["proof_status"]
                != "python-simulated-winning-actions"):
            raise StudioError("companion practice lacks canonical winning proof")
        prefix = f"practice/slot-{index:02d}"
        for relative, payload in practice_package.files.items():
            practice_files[f"{prefix}/{relative}"] = payload
        practice.append(CompanionPractice(
            seed=sample.seed,
            intent_digest=canonical_digest(sample.to_payload()),
            world_digest=str(practice_package.manifest["world_digest"]),
            proof_digest=str(practice_package.manifest["proof_digest"]),
            winning_steps=winning_steps,
            capability_xp=insight.verified_experience,
            insight_digest=insight.digest,
            challenge_score=insight.challenge_score,
            mirror_report_digest=individual_mirror.digest,
            mirror_attempts=len(individual_mirror.probes),
            package_manifest_digest=str(practice_package.manifest["manifest_digest"]),
            package_path=prefix,
        ))
    earlier_stages: tuple[StudioStage, ...] = ()
    if project.cleared_research is not None:
        cleared = project.cleared_research.to_payload()
        earlier_stages = (
            StudioStage(
                "reviewed_research",
                str(cleared["research_brief_digest"]),
                str(cleared["packet_digest"]),
                plan.digest,
                str(cleared["rights_ledger_digest"]),
            ),
        )
    stages = earlier_stages + (
        StudioStage("original", canonical_digest(intent.to_payload()),
                    project.world.digest, plan.digest,
                    canonical_digest({"algorithm": project.world.algorithm, "source": source})),
        StudioStage("stepping_stone", project.world.digest,
                    project.proof.digest, plan.digest,
                    canonical_digest(project.receipt())),
        StudioStage("consumer_source_candidate", project.proof.digest,
                    str(package.manifest["manifest_digest"]), plan.digest, mirror.digest),
    )
    if living_package is not None and living_mirror is not None:
        stages = (
            *stages[:-1],
            StudioStage(
                "living_world",
                canonical_digest(story_intent.payload()),
                living_package.manifest["world_digest"],
                plan.digest,
                living_mirror.digest,
            ),
            stages[-1],
        )
    # Never accept an operator-supplied boolean as a substitute for independent
    # legal, platform, human, performance, store, safety or signing evidence.
    consumer = ConsumerReview(
        original_source=True,  # world geometry and runnable code stay original
        canonical_proof=project.proof.final_state.status == "won",
        mirror_passed=mirror.passed,
        rights_reviewed=False,
        human_playtested=False,
        platform_hardware_tested=False,
        accessibility_reviewed=False,
        localization_reviewed=False,
        malware_scan_passed=False,
        code_signed=False,
        platform_permission_verified=False,
        approved_for_publication=False,
    )
    metadata = {
        "studio/pipeline.json": {
            "schema": "skeleton.game_builder.studio_pipeline.v1",
            "source": source,
            "project_id": intent.project_id,
            "stages": [stage.to_payload() for stage in stages],
            "rights_reference_only": project.cleared_research is not None,
            "research_packet_digest": (
                project.cleared_research.to_payload()["packet_digest"]
                if project.cleared_research is not None else None
            ),
            "original_game_claim": "generated-or-user-authored-geometry",
            "not_automatically_published": True,
        },
        "studio/jeeves_dragon_tools.json": plan.to_payload(),
        "studio/executed_tool_receipts.json": execution_audit,
        "studio/mirror_room.json": mirror.to_payload(),
        "studio/consumer_gate.json": consumer.to_payload(),
        "studio/companion_mirror_room.json": {
            "schema": "skeleton.game_builder.companion_mirror_cohort.v1",
            "reports": [report.to_payload() for report in companion_mirrors],
            "all_passed": all(report.passed for report in companion_mirrors),
            "native_hardware_playtests": False,
            "copyright_similarity_cleared": False,
        },
        "studio/companion_almanac.json": {
            "schema": "skeleton.game_builder.companion_machine_almanac.v1",
            "insights": [item.to_payload() for item in almanac_insights],
            "parent_world_digest": project.world.digest,
            "unique_themes": diversity_count,
            "source_kind": "measured_local_original_gameplay",
            "open_world_or_npc_quality_verified": False,
            "human_playtests": False,
            "trained_model_weights": False,
        },
        "studio/companion_practice.json": {
            "schema": "skeleton.game_builder.companion_practice.v1",
            "games": [item.to_payload() for item in practice],
            "capability_xp": sum(item.capability_xp for item in practice),
            "not_model_training": True,
            "not_imported_game_expression": True,
        },
    }
    if tiled_import_receipt is not None:
        metadata["studio/tiled_import.json"] = tiled_import_receipt
    if authored_story is not None:
        metadata["studio/living_story_authoring.json"] = authored_story.evidence()
    if living_package is not None and living_mirror is not None:
        metadata["studio/living_story_mirror.json"] = living_mirror.payload()
        metadata["studio/living_story_almanac.json"] = {
            "schema": "skeleton.game_builder.living_story_almanac.v1",
            "source_kind": "measured_original_simulation",
            "world_digest": living_mirror.world_digest,
            "proof_digest": living_mirror.proof_digest,
            "package_digest": living_package.digest,
            "mirror_digest": living_mirror.digest,
            "NPC_count": living_package.manifest["npc_count"],
            "region_count": living_package.manifest["regions"],
            "quest_count": living_package.manifest["quest_count"],
            "ending": living_package.manifest["ending"],
            "world_mode": living_package.manifest["mode"],
            "externally_trained_model": False,
            "human_playtested": False,
            "native_hardware_cleared": False,
        }
    new_files = dict(package.files)
    new_files.pop("release.json")
    new_files.update(practice_files)
    if living_package is not None:
        for relative, payload in living_package.files.items():
            new_files["living_story/" + relative] = payload
    for path, item in metadata.items():
        new_files[path] = _stable_bytes(item)
    if sum(len(data) for data in new_files.values()) > 16_000_000:
        raise StudioError("studio package exceeds source resource budget")
    manifest_body = {
        k: v for k, v in package.manifest.items()
        if k not in {"files", "manifest_digest"}
    }
    manifest_body["schema"] = "skeleton.game_builder.studio_package.v1"
    manifest_body["files"] = {
        path: sha256(data).hexdigest()
        for path, data in sorted(new_files.items())
    }
    manifest = {**manifest_body, "manifest_digest": canonical_digest(manifest_body)}
    new_files["release.json"] = _stable_bytes(manifest)
    enhanced = DualRuntimePackage(new_files, manifest)
    run = StudioRun(
        project=project, source=source, stages=stages,
        tool_plan=plan, mirror=mirror, consumer=consumer,
        practice=tuple(practice), package=enhanced,
        narrative=living_package, narrative_mirror=living_mirror,
    )
    return run


def export_studio_run(run: StudioRun, destination: str, *, authorized: bool):
    """Use the canonical atomic exporter; source export is not store publication."""
    if not authorized:
        raise PermissionError("game studio export requires authorization")
    if not isinstance(run, StudioRun) or not run.mirror.passed:
        raise StudioError("only adversarially reviewed studio runs may be exported")
    return export_dual_runtime_package(run.package, destination, authorized=True)


__all__ = [
    "StudioError", "StudioStage", "ConsumerReview", "CompanionPractice",
    "StudioRun", "run_original_game_studio", "export_studio_run",
]
