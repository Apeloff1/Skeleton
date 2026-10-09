"""Compile original playable games from explicit designer intent and reviewed research.

Original level geometry is generated before optional source-rights clearance. A
reviewed research brief can influence the *design process*, but source text is
never code, game rules, runtime scripts or training data in this compiler.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .contracts import canonical_digest
from .knowledge_rights_bridge import (
    ClearedResearchPacket, clear_research_for_design,
    require_cleared_research_current,
)
from .reviewed_knowledge import KnowledgeBrief, ReviewedKnowledgeStore
from .rights import RightsLedger
from .playable_export import PlayableHTML, render_playable_world, write_playable_html
from .playable_simulation import GameReplay, demonstrate_solvable
from .playable_world import GameBuildIntent, PlayableWorld, generate_playable_world


class PlayableCompilationError(ValueError):
    """Original game output failed authorization or consistency conditions."""


@dataclass(frozen=True, slots=True)
class CompiledPlayableProject:
    world: PlayableWorld
    playable: PlayableHTML
    proof: GameReplay
    cleared_research: ClearedResearchPacket | None
    target_runtime: str = "offline-html5"

    def __post_init__(self) -> None:
        if not isinstance(self.world, PlayableWorld) or not isinstance(self.playable, PlayableHTML):
            raise PlayableCompilationError("typed generated world and HTML required")
        if not isinstance(self.proof, GameReplay):
            raise PlayableCompilationError("executable solvability proof required")
        if self.playable.world_digest != self.world.digest:
            raise PlayableCompilationError("HTML does not implement this world")
        if self.proof.world_digest != self.world.digest or self.proof.final_state.status != "won":
            raise PlayableCompilationError("playable game lacks a winning replay proof")
        if self.playable.proof_digest != self.proof.digest:
            raise PlayableCompilationError("HTML proof digest mismatch")
        if self.cleared_research is not None:
            if not isinstance(self.cleared_research, ClearedResearchPacket):
                raise PlayableCompilationError("typed independent research clearance required")
            if self.cleared_research.project_id != self.world.intent.project_id:
                raise PlayableCompilationError("cross-project research clearance rejected")
            if self.cleared_research.artifact_digest != self.world.digest:
                raise PlayableCompilationError("research clearance targets another generated game")
            if self.playable.research_packet_digest != self.cleared_research.to_payload()["packet_digest"]:
                raise PlayableCompilationError("rendered source citations differ from clearance")
        elif self.playable.research_packet_digest is not None:
            raise PlayableCompilationError("game reports unqualified research citations")
        if self.target_runtime != "offline-html5":
            raise PlayableCompilationError("unsupported game platform")

    def receipt(self) -> dict[str, object]:
        body: dict[str, object] = {
            "schema": "skeleton.game_builder.compiled_playable.v1",
            "project_id": self.world.intent.project_id,
            "target_runtime": self.target_runtime,
            "source_world_digest": self.world.digest,
            "html_sha256": self.playable.html_sha256,
            "replay_proof_digest": self.proof.digest,
            "replay_proof_steps": self.proof.final_state.steps,
            "levels": len(self.world.levels),
            "research_clearance_digest": (
                self.cleared_research.to_payload()["packet_digest"]
                if self.cleared_research is not None else None
            ),
            "rights_reference_only": self.cleared_research is not None,
            "original_geometric_assets": True,
            "network_calls": False,
            "model_training": False,
            "publication_authority": False,
            "validated_gameplay_proof": True,
        }
        return {**body, "receipt_digest": canonical_digest(body)}


def compile_original_game(
    intent: GameBuildIntent,
    *,
    authorized: bool,
) -> CompiledPlayableProject:
    """Generate an original browser game with a verified winning move trace."""
    if not authorized:
        raise PermissionError("local game compilation requires authorization")
    world = generate_playable_world(intent, authorized=True)
    proof = demonstrate_solvable(world, authorized=True)
    html = render_playable_world(world, authorized=True)
    return CompiledPlayableProject(world, html, proof, None)


def compile_game_from_reviewed_research(
    library: ReviewedKnowledgeStore,
    brief: KnowledgeBrief,
    rights: RightsLedger,
    intent: GameBuildIntent,
    *,
    human_approved: bool,
    authorized: bool,
) -> CompiledPlayableProject:
    """Compile original game and attach independently cleared ideas references.

    The world generator is not prompted with source instructions. The packet's
    approval is bound to the generated world digest and exact source identities.
    """
    if not authorized:
        raise PermissionError("research-backed compilation requires authorization")
    if type(human_approved) is not bool or not human_approved:
        raise PlayableCompilationError("human design approval required")
    if not isinstance(intent, GameBuildIntent):
        raise PlayableCompilationError("typed original game intent required")
    if not isinstance(library, ReviewedKnowledgeStore) or not isinstance(rights, RightsLedger):
        raise PlayableCompilationError("canonical knowledge and rights owners required")
    if not isinstance(brief, KnowledgeBrief) or brief.owner == "":
        raise PlayableCompilationError("human-reviewed knowledge brief required")

    world = generate_playable_world(intent, authorized=True)
    proof = demonstrate_solvable(world, authorized=True)
    # Build original standalone output first; errors in game generation do not
    # mutate the canonical RightsLedger.
    render_playable_world(world, authorized=True)
    clearance = clear_research_for_design(
        library, brief, rights,
        project_id=intent.project_id, artifact_digest=world.digest,
        human_approved=human_approved, authorized=True,
    )
    require_cleared_research_current(clearance, library, rights, authorized=True)
    html = render_playable_world(
        world, research_packet=clearance, authorized=True,
    )
    return CompiledPlayableProject(world, html, proof, clearance)


def export_compiled_project(
    project: CompiledPlayableProject,
    destination: str | Path,
    *,
    authorized: bool,
) -> Path:
    if not authorized:
        raise PermissionError("game bundle export requires authorization")
    if not isinstance(project, CompiledPlayableProject):
        raise PlayableCompilationError("typed game compiler output required")
    # Only original generated JavaScript/HTML is written, not research bodies.
    return write_playable_html(project.playable, destination, authorized=True)


__all__ = [
    "PlayableCompilationError", "CompiledPlayableProject",
    "compile_original_game", "compile_game_from_reviewed_research",
    "export_compiled_project",
]
