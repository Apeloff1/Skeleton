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

from .contracts import canonical_digest
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
        })


def _practice_intents(base: GameBuildIntent, count: int) -> tuple[GameBuildIntent, ...]:
    from dataclasses import replace
    if type(count) is not int or not 0 <= count <= 8:
        raise StudioError("companion practice batch must have 0 to 8 real games")
    samples: list[GameBuildIntent] = []
    for i in range(count):
        seed = int(canonical_digest({
            "practice_parent": base.to_payload(), "index": i,
            "algorithm": "skeleton.original_practice.v1",
        })[:15], 16)
        # Preserve identity uniqueness even for a maximum-length project ID.
        # The digest also prevents truncation collisions across parent games.
        parent_prefix = base.project_id[:100].rstrip("._:-")
        derived_id = f"{parent_prefix}.p-{canonical_digest(base.to_payload())[:12]}-{i + 1}"
        samples.append(replace(
            base, project_id=derived_id,
            title=f"Practice {i + 1}: {base.title}"[:120],
            seed=seed,
            hazards_per_level=min(base.hazards_per_level + i % 3, 24),
        ))
    return tuple(samples)


def run_original_game_studio(
    intent: GameBuildIntent,
    *,
    authorized: bool,
    human_reviewed_tiles: tuple[object, ...] | list[object] | None = None,
    human_authored_approved: bool = False,
    reviewed_library: object | None = None,
    research_brief: object | None = None,
    rights_ledger: object | None = None,
    human_research_approved: bool = False,
    mirror_attempts: int = 128,
    companion_practice_games: int = 2,
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
    if human_reviewed_tiles is None and human_authored_approved:
        raise StudioError("authored approval cannot be applied to generated levels")
    research_enabled = any(
        value is not None for value in (reviewed_library, research_brief, rights_ledger)
    ) or human_research_approved
    if research_enabled:
        if (reviewed_library is None or research_brief is None or rights_ledger is None
                or type(human_research_approved) is not bool
                or not human_research_approved):
            raise StudioError("research requires reviewed library, brief, rights and human approval")
        if human_reviewed_tiles is not None:
            raise StudioError("authored editor games need independent rights handoff")
    if human_reviewed_tiles is not None and not human_authored_approved:
        raise StudioError("manually authored geometry requires human review")
    if fabric is None:
        fabric = ToolFabric()
    if not isinstance(fabric, ToolFabric):
        raise StudioError("typed game-tool fabric required")
    source = ("original-authored" if human_reviewed_tiles is not None
              else "original-research-referenced" if research_enabled
              else "original-generated")
    work = [
        (Actor.JEEVES, Phase.ORIGINAL, "world.authored" if human_reviewed_tiles is not None else "world.generate"),
        (Actor.DRAGON, Phase.STEPPING_STONE, "game.simulate"),
        (Actor.DRAGON, Phase.STEPPING_STONE, "game.browser"),
        (Actor.DRAGON, Phase.STEPPING_STONE, "game.godot"),
        (Actor.COMPANION, Phase.STEPPING_STONE, "companion.practice"),
        (Actor.MIRROR, Phase.REVIEW, "mirror.fuzz"),
        (Actor.JEEVES, Phase.CONSUMER, "release.assess"),
        (Actor.JEEVES, Phase.CONSUMER, "package.source"),
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
    if human_reviewed_tiles is not None:
        project = compile_authored_game(intent, human_reviewed_tiles,
                                        human_reviewed=True, authorized=True)
    elif research_enabled:
        from .playable_compiler import compile_game_from_reviewed_research
        # The compiler independently verifies source revisions, RightsLedger
        # decisions and project-bound reference-only authorization.
        project = compile_game_from_reviewed_research(
            reviewed_library, research_brief, rights_ledger, intent,
            human_approved=True, authorized=True,
        )
    else:
        project = compile_original_game(intent, authorized=True)
    package = render_dual_runtime_package(project, authorized=True)
    mirror = review_playable_project(project, package, authorized=True,
                                    attempts=mirror_attempts)
    if not mirror.passed:
        raise StudioError("adversarial game mirror room found a failure")
    practice: list[CompanionPractice] = []
    practice_files: dict[str, bytes] = {}
    for index, sample in enumerate(_practice_intents(intent, companion_practice_games), 1):
        candidate = compile_original_game(sample, authorized=True)
        # Companion games are independently playable browser/Godot products,
        # not just names and XP. Each receives a complete canonical package
        # and a separate manifest, proof, editor and verified world.
        practice_package = render_dual_runtime_package(candidate, authorized=True)
        prefix = f"practice/slot-{index:02d}"
        for relative, payload in practice_package.files.items():
            practice_files[f"{prefix}/{relative}"] = payload
        practice.append(CompanionPractice(
            seed=sample.seed,
            intent_digest=canonical_digest(sample.to_payload()),
            world_digest=candidate.world.digest,
            proof_digest=candidate.proof.digest,
            winning_steps=candidate.proof.final_state.steps,
            capability_xp=25 + len(candidate.world.levels) * 5,
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
        "studio/mirror_room.json": mirror.to_payload(),
        "studio/consumer_gate.json": consumer.to_payload(),
        "studio/companion_practice.json": {
            "schema": "skeleton.game_builder.companion_practice.v1",
            "games": [item.to_payload() for item in practice],
            "capability_xp": sum(item.capability_xp for item in practice),
            "not_model_training": True,
            "not_imported_game_expression": True,
        },
    }
    new_files = dict(package.files)
    new_files.pop("release.json")
    new_files.update(practice_files)
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
