"""Original quest/scene production pipeline and consumer evidence package."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from .contracts import canonical_digest, canonical_json
from .quest_scene_engine import DirectorError, DirectorWorld
from .quest_scene_export import render_director_browser
from .quest_director_solver import solve_quest, compare_solution_routes
from .quest_scene_mirror import DirectorMirrorReport, review_director


def _json_bytes(value) -> bytes:
    return (canonical_json(value) + "\n").encode()


@dataclass(frozen=True, slots=True)
class DirectorStudioProduct:
    world_digest: str
    main_proof_digest: str
    mirror: DirectorMirrorReport
    files: dict[str, bytes]
    manifest: dict[str, object]

    @property
    def digest(self):
        return self.manifest["manifest_digest"]

    def receipt(self):
        return {
            "schema": "skeleton.game_builder.director_studio_receipt.v1",
            "world_digest": self.world_digest,
            "main_proof_digest": self.main_proof_digest,
            "mirror_digest": self.mirror.digest,
            "source_manifest_digest": self.digest,
            "playable": True,
            "browser_playtested": False,
            "native_executable": False,
            "commercial_publication_approved": False,
        }


def build_director_studio(
    world: DirectorWorld, *, authorized: bool,
    mirror_attempts: int = 128,
) -> DirectorStudioProduct:
    if not authorized:
        raise PermissionError("original quest studio requires operator authority")
    if not isinstance(world, DirectorWorld):
        raise DirectorError("typed original authored quest world required")
    if type(mirror_attempts) is not int or not 64 <= mirror_attempts <= 512:
        raise DirectorError("invalid explicit adversarial review budget")
    main = next(q for q in world.quests if q.scope == "main")
    witness = solve_quest(world, main.key, strategy="creative", authorized=True)
    methods = compare_solution_routes(world, main.key, authorized=True)
    browser = render_director_browser(world, authorized=True)
    mirror = review_director(
        world, witness.replay, browser=browser.html,
        authorized=True, attempts=mirror_attempts,
    )
    if not mirror.passed:
        raise DirectorError("adversarial quest and scene mirror rejected game source")
    files = {
        "index.html": browser.html,
        "editor/complete_scene_blueprint.json": _json_bytes(world.payload()),
        "game/world.json": _json_bytes(world.payload()),
        "game/main_story_proof.json": _json_bytes(witness.replay.payload()),
        "game/alternative_solutions.json": _json_bytes(methods),
        "review/mirror_room.json": _json_bytes(mirror.payload()),
        "review/consumer_gate.json": _json_bytes({
            "schema": "skeleton.game_builder.quest_consumer_review.v1",
            "status": "release-blocked",
            "missing": [
                "human_playtesting", "copyright_similarity", "accessibility",
                "localization", "native_engine_port", "hardware_tests",
                "malware_scan", "performance", "publisher_signoff",
            ],
            "native_release_verified": False,
        }),
        "almanac/observations.json": _json_bytes({
            "schema": "skeleton.game_builder.quest_director_almanac.v1",
            "world_digest": world.digest,
            "original_scene_count": len(world.scenes),
            "quest_count": len(world.quests),
            "stage_count": sum(len(q.stages) for q in world.quests),
            "cutscene_count": sum(len(s.cutscenes) for s in world.scenes),
            "cutscene_cue_count": sum(len(c.cues) for s in world.scenes
                                     for c in s.cutscenes),
            "alternative_methods": methods,
            "mirror_digest": mirror.digest,
            "trained_weights": False,
            "human_subjective_rating": None,
        }),
        "README.md": (
            "# Original Quest and Scene Director\n"
            "Open index.html offline. Every actor, scene, camera, lighting, "
            "timeline cue, quest stage, optional goal and solution condition "
            "is editable in editor/complete_scene_blueprint.json.\n"
            "Rebuild after human originality review. Browser output is a "
            "preview, not a native release or commercial permission.\n"
        ).encode(),
    }
    if sum(len(data) for data in files.values()) > 4_000_000:
        raise DirectorError("quest game output exceeds source package budget")
    manifest = {
        "schema": "skeleton.game_builder.director_source_release.v1",
        "world_digest": world.digest,
        "main_proof_digest": witness.replay.digest,
        "mirror_digest": mirror.digest,
        "scene_count": len(world.scenes),
        "quest_count": len(world.quests),
        "cutscene_count": sum(len(s.cutscenes) for s in world.scenes),
        "browser_sha256": browser.source_sha256,
        "publication_approved": False,
        "native_build_validated": False,
        "files": {name: sha256(data).hexdigest()
                  for name, data in sorted(files.items())},
    }
    manifest["manifest_digest"] = canonical_digest(manifest)
    files["release.json"] = _json_bytes(manifest)
    return DirectorStudioProduct(
        world.digest, witness.replay.digest, mirror, files, manifest,
    )


__all__ = ["DirectorStudioProduct", "build_director_studio"]
