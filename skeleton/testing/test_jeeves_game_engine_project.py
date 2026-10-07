from __future__ import annotations

import json

import pytest

from skeleton.jeeves.core import Jeeves
from skeleton.jeeves.game_engine_assets import (
    canonical_asset_sources,
)
from skeleton.jeeves.game_engine_audio import (
    AudioPosition,
    AudioSceneSource,
    canonical_audio_source,
)
from skeleton.jeeves.game_engine_animation import (
    AnimationSceneSource,
    canonical_animation_source,
)
from skeleton.jeeves.game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    SandboxPatch,
)
from skeleton.jeeves.game_engine_scripts import (
    canonical_script_sources,
)
from skeleton.jeeves.game_engine_physics import (
    PhysicsSceneSource,
    Vec3,
    canonical_physics_source,
)
from skeleton.jeeves.game_engine_project import (
    AdversarialGameProjectEvolution,
    ExecutableGameProjectLab,
    ProjectEvolutionSession,
    build_executable_game_project,
)


@pytest.mark.parametrize(
    "era",
    list(EngineEra),
)
def test_complete_project_passes_all_six_quality_planes(
    era: EngineEra,
) -> None:
    lab = ExecutableGameProjectLab()
    project = lab.create(
        era,
        "action_adventure",
    )

    report = lab.evaluate(
        project
    )

    assert report.passed
    assert report.score == 1.0
    assert report.runtime_score == 1.0
    assert report.asset_score == 1.0
    assert report.script_score == 1.0
    assert report.physics_score == 1.0
    assert report.audio_score == 1.0
    assert report.animation_score == 1.0
    assert report.failed == ()


def test_project_builder_uses_all_canonical_evidence_sources_by_default() -> None:
    project = (
        build_executable_game_project(
            EngineEra.EIGHT_BIT,
            "platformer",
        )
    )

    assert (
        project.sources
        == canonical_asset_sources(
            EngineEra.EIGHT_BIT
        )
    )
    assert (
        "assets/compiled/manifest.json"
        in project.tree.files
    )
    assert (
        project.scripts
        == canonical_script_sources(
            EngineEra.EIGHT_BIT
        )
    )
    assert (
        "scripts/compiled/manifest.json"
        in project.tree.files
    )
    assert (
        project.physics
        == canonical_physics_source(
            EngineEra.EIGHT_BIT
        )
    )
    assert (
        "physics/compiled/manifest.json"
        in project.tree.files
    )
    assert (
        project.audio
        == canonical_audio_source(
            EngineEra.EIGHT_BIT
        )
    )
    assert (
        "audio/compiled/manifest.json"
        in project.tree.files
    )
    assert (
        project.animation
        == canonical_animation_source(
            EngineEra.EIGHT_BIT
        )
    )
    assert (
        "animation/compiled/manifest.json"
        in project.tree.files
    )


def test_runtime_fix_cannot_hitchhike_asset_regression() -> None:
    lab = ExecutableGameProjectLab()
    project = lab.create(
        EngineEra.EIGHT_BIT
    )
    tuning_path = (
        "engine/legacy_tuning.json"
    )
    tuning = json.loads(
        project.tree.read(
            tuning_path
        )
    )
    tuning["jump_impulse"] = 999
    broken = project.apply(
        (
            SandboxPatch(
                tuning_path,
                json.dumps(tuning),
                project.tree.file_digest(
                    tuning_path
                ),
            ),
        )
    )
    before = lab.evaluate(
        broken
    )
    assert (
        before.runtime_score < 1.0
    )
    assert before.asset_score == 1.0

    runtime_repair = (
        lab.engine_lab.canonical_repair(
            broken.engine,
            before.runtime,
        )
    )
    manifest_path = (
        "assets/compiled/manifest.json"
    )
    manifest = json.loads(
        broken.tree.read(
            manifest_path
        )
    )
    manifest["asset_count"] += 1
    poison = SandboxPatch(
        manifest_path,
        json.dumps(manifest),
        broken.tree.file_digest(
            manifest_path
        ),
    )

    evolution = (
        AdversarialGameProjectEvolution(
            lab
        )
    )
    session = evolution.start(
        broken
    )
    (
        next_session,
        report,
        round_result,
    ) = evolution.tournament_round(
        session,
        (
            runtime_repair
            + (poison,),
        ),
    )

    assert not round_result.accepted
    assert report == before
    assert (
        next_session.sandbox.tree.digest
        == broken.tree.digest
    )


def test_asset_fix_cannot_hitchhike_runtime_regression() -> None:
    lab = ExecutableGameProjectLab()
    project = lab.create(
        EngineEra.SIXTEEN_BIT
    )
    manifest_path = (
        "assets/compiled/manifest.json"
    )
    manifest = json.loads(
        project.tree.read(
            manifest_path
        )
    )
    manifest["asset_count"] += 1
    broken = project.apply(
        (
            SandboxPatch(
                manifest_path,
                json.dumps(manifest),
                project.tree.file_digest(
                    manifest_path
                ),
            ),
        )
    )
    before = lab.evaluate(
        broken
    )
    assert before.runtime_score == 1.0
    assert before.asset_score < 1.0

    asset_repair = tuple(
        patch
        for patch
        in lab.canonical_repair(
            broken,
            before,
        )
        if patch.path.startswith(
            "assets/compiled/"
        )
    )
    tuning_path = (
        "engine/legacy_tuning.json"
    )
    tuning = json.loads(
        broken.tree.read(
            tuning_path
        )
    )
    tuning["paddle_speed"] = (
        tuning.get(
            "paddle_speed",
            4,
        )
    )
    # Sixteen-bit has no paddle_speed; introducing an extra tuning key makes
    # the runtime compiler fail closed without colliding with asset repair.
    runtime_poison = SandboxPatch(
        tuning_path,
        json.dumps(
            {
                **tuning,
                "rogue_key": 1,
            }
        ),
        broken.tree.file_digest(
            tuning_path
        ),
    )

    evolution = (
        AdversarialGameProjectEvolution(
            lab
        )
    )
    session = evolution.start(
        broken
    )
    (
        next_session,
        report,
        round_result,
    ) = evolution.tournament_round(
        session,
        (
            asset_repair
            + (
                runtime_poison,
            ),
        ),
    )

    assert not round_result.accepted
    assert report == before
    assert (
        next_session.sandbox.tree.digest
        == broken.tree.digest
    )


def test_canonical_project_repair_heals_all_six_planes_together() -> None:
    lab = ExecutableGameProjectLab()
    project = lab.create(
        EngineEra.EARLY_3D,
        "immersive_sim",
    )
    tuning_path = (
        "engine/3d_tuning.json"
    )
    tuning = json.loads(
        project.tree.read(
            tuning_path
        )
    )
    tuning["near_plane"] = 999

    manifest_path = (
        "assets/compiled/manifest.json"
    )
    manifest = json.loads(
        project.tree.read(
            manifest_path
        )
    )
    manifest["asset_count"] += 2

    script_manifest_path = (
        "scripts/compiled/manifest.json"
    )
    script_manifest = json.loads(
        project.tree.read(
            script_manifest_path
        )
    )
    script_manifest["script_count"] += 1

    physics_manifest_path = (
        "physics/compiled/manifest.json"
    )
    physics_manifest = json.loads(
        project.tree.read(
            physics_manifest_path
        )
    )
    physics_manifest["manifest_digest"] = "0" * 64

    audio_manifest_path = (
        "audio/compiled/manifest.json"
    )
    audio_manifest = json.loads(
        project.tree.read(
            audio_manifest_path
        )
    )
    audio_manifest["manifest_digest"] = "f" * 64

    animation_manifest_path = (
        "animation/compiled/manifest.json"
    )
    animation_manifest = json.loads(
        project.tree.read(
            animation_manifest_path
        )
    )
    animation_manifest[
        "manifest_digest"
    ] = "a" * 64

    broken = project.apply(
        (
            SandboxPatch(
                tuning_path,
                json.dumps(tuning),
                project.tree.file_digest(
                    tuning_path
                ),
            ),
            SandboxPatch(
                manifest_path,
                json.dumps(manifest),
                project.tree.file_digest(
                    manifest_path
                ),
            ),
            SandboxPatch(
                script_manifest_path,
                json.dumps(
                    script_manifest
                ),
                project.tree.file_digest(
                    script_manifest_path
                ),
            ),
            SandboxPatch(
                physics_manifest_path,
                json.dumps(
                    physics_manifest
                ),
                project.tree.file_digest(
                    physics_manifest_path
                ),
            ),
            SandboxPatch(
                audio_manifest_path,
                json.dumps(
                    audio_manifest
                ),
                project.tree.file_digest(
                    audio_manifest_path
                ),
            ),
            SandboxPatch(
                animation_manifest_path,
                json.dumps(
                    animation_manifest
                ),
                project.tree.file_digest(
                    animation_manifest_path
                ),
            ),
        )
    )
    before = lab.evaluate(
        broken
    )
    assert not before.passed
    assert (
        before.runtime_score < 1.0
    )
    assert before.asset_score < 1.0
    assert before.script_score < 1.0
    assert before.physics_score < 1.0
    assert before.audio_score < 1.0
    assert before.animation_score < 1.0

    evolution = (
        AdversarialGameProjectEvolution(
            lab
        )
    )
    session = evolution.start(
        broken
    )
    result = evolution.evolve(
        session,
        evolution.canonical_candidates,
        target=1.0,
        max_rounds=4,
    )

    assert result.target_met
    assert result.report.passed
    assert len(result.rounds) == 1
    assert result.rounds[0].accepted
    assert len(
        result.session.checkpoints
    ) == 2
    assert (
        result.session.verify_lineage()
    )


def test_untracked_compiled_asset_is_removed_by_project_repair() -> None:
    lab = ExecutableGameProjectLab()
    project = lab.create(
        EngineEra.MODERN
    )
    rogue_path = (
        "assets/compiled/"
        "untracked.mesh.json"
    )
    broken = project.apply(
        (
            SandboxPatch(
                rogue_path,
                "{}",
            ),
        )
    )

    before = lab.evaluate(
        broken
    )

    assert not before.passed
    assert (
        "assets:inventory"
        in before.failed
    )

    patches = lab.canonical_repair(
        broken,
        before,
    )
    repaired = broken.apply(
        patches
    )

    assert lab.evaluate(
        repaired
    ).passed
    assert (
        rogue_path
        not in repaired.tree.files
    )


def test_project_source_recipes_are_frozen_within_lineage() -> None:
    lab = ExecutableGameProjectLab()
    project = lab.create(
        EngineEra.PONG
    )
    session = (
        ProjectEvolutionSession.start(
            project
        )
    )
    different = lab.create(
        EngineEra.PONG,
        sources=(),
    )

    with pytest.raises(
        GameEngineLabError,
        match="source recipes",
    ):
        session.checkpoint(
            different
        )


def test_project_restore_truncates_future_lineage() -> None:
    lab = ExecutableGameProjectLab()
    project = lab.create(
        EngineEra.SHADER
    )
    path = "engine/3d_tuning.json"
    tuning = json.loads(
        project.tree.read(path)
    )
    tuning["fov_deg"] = 999
    broken = project.apply(
        (
            SandboxPatch(
                path,
                json.dumps(tuning),
                project.tree.file_digest(
                    path
                ),
            ),
        )
    )

    evolution = (
        AdversarialGameProjectEvolution(
            lab
        )
    )
    session = evolution.start(
        broken
    )
    report = lab.evaluate(
        broken
    )
    repair = lab.canonical_repair(
        broken,
        report,
    )
    promoted, selected, result = (
        evolution.tournament_round(
            session,
            (repair,),
        )
    )

    assert result.accepted
    assert selected.passed
    assert len(
        promoted.checkpoints
    ) == 2

    restored = promoted.restore(0)

    assert len(
        restored.checkpoints
    ) == 1
    assert restored.sequence == 1
    assert (
        restored.verify_lineage()
    )


def test_equal_quality_project_churn_is_rejected() -> None:
    lab = ExecutableGameProjectLab()
    project = lab.create(
        EngineEra.NEXT
    )
    evolution = (
        AdversarialGameProjectEvolution(
            lab
        )
    )
    session = evolution.start(
        project
    )

    (
        next_session,
        report,
        round_result,
    ) = evolution.tournament_round(
        session,
        (
            (
                SandboxPatch(
                    "notes/cosmetic.txt",
                    "no quality change",
                ),
            ),
        ),
    )

    assert report.passed
    assert not round_result.accepted
    assert (
        next_session.sandbox.tree.digest
        == project.tree.digest
    )



def test_jeeves_owns_complete_project_lab_lazily() -> None:
    jeeves = Jeeves()

    assert jeeves._game_projects is None

    project = jeeves.build_game_project(
        EngineEra.OPEN_WORLD,
        gameplay_dialect="immersive_sim",
    )

    assert jeeves._game_projects is not None
    report = jeeves.evaluate_game_project(
        project
    )
    assert report.passed
    assert report.runtime_score == 1.0
    assert report.asset_score == 1.0
    assert report.script_score == 1.0
    assert report.physics_score == 1.0
    assert report.audio_score == 1.0
    assert report.animation_score == 1.0


def test_jeeves_evolves_complete_project_to_six_plane_target() -> None:
    jeeves = Jeeves()
    project = jeeves.build_game_project(
        EngineEra.PONG
    )
    manifest_path = (
        "assets/compiled/manifest.json"
    )
    manifest = json.loads(
        project.tree.read(
            manifest_path
        )
    )
    manifest["asset_count"] += 1
    broken = project.apply(
        (
            SandboxPatch(
                manifest_path,
                json.dumps(manifest),
                project.tree.file_digest(
                    manifest_path
                ),
            ),
        )
    )

    assert not (
        jeeves.evaluate_game_project(
            broken
        ).passed
    )

    result = jeeves.evolve_game_project(
        broken,
        target=1.0,
        max_rounds=4,
    )

    assert result.target_met
    assert result.report.passed
    assert len(result.rounds) == 1
    assert result.rounds[0].accepted
    assert result.session.verify_lineage()



def test_script_fix_cannot_hitchhike_asset_regression() -> None:
    lab = ExecutableGameProjectLab()
    project = lab.create(
        EngineEra.MODERN
    )
    script_manifest_path = (
        "scripts/compiled/manifest.json"
    )
    script_manifest = json.loads(
        project.tree.read(
            script_manifest_path
        )
    )
    script_manifest["script_count"] += 1
    broken = project.apply(
        (
            SandboxPatch(
                script_manifest_path,
                json.dumps(
                    script_manifest
                ),
                project.tree.file_digest(
                    script_manifest_path
                ),
            ),
        )
    )
    before = lab.evaluate(
        broken
    )
    assert before.runtime_score == 1.0
    assert before.asset_score == 1.0
    assert before.script_score < 1.0

    script_repair = tuple(
        patch
        for patch
        in lab.canonical_repair(
            broken,
            before,
        )
        if patch.path.startswith(
            "scripts/compiled/"
        )
    )
    asset_manifest_path = (
        "assets/compiled/manifest.json"
    )
    asset_manifest = json.loads(
        broken.tree.read(
            asset_manifest_path
        )
    )
    asset_manifest["asset_count"] += 1
    asset_poison = SandboxPatch(
        asset_manifest_path,
        json.dumps(
            asset_manifest
        ),
        broken.tree.file_digest(
            asset_manifest_path
        ),
    )

    evolution = AdversarialGameProjectEvolution(
        lab
    )
    session = evolution.start(
        broken
    )
    (
        next_session,
        report,
        round_result,
    ) = evolution.tournament_round(
        session,
        (
            script_repair
            + (asset_poison,),
        ),
    )

    assert not round_result.accepted
    assert report == before
    assert (
        next_session.sandbox.tree.digest
        == broken.tree.digest
    )


def test_project_script_recipes_are_frozen_within_lineage() -> None:
    lab = ExecutableGameProjectLab()
    project = lab.create(
        EngineEra.HD
    )
    session = ProjectEvolutionSession.start(
        project
    )
    different = lab.create(
        EngineEra.HD,
        scripts=(),
    )

    with pytest.raises(
        GameEngineLabError,
        match="script recipes",
    ):
        session.checkpoint(
            different
        )


def test_untracked_compiled_script_is_removed_by_project_repair() -> None:
    lab = ExecutableGameProjectLab()
    project = lab.create(
        EngineEra.NEXT
    )
    rogue_path = (
        "scripts/compiled/"
        "untracked.script.json"
    )
    broken = project.apply(
        (
            SandboxPatch(
                rogue_path,
                "{}",
            ),
        )
    )

    before = lab.evaluate(
        broken
    )

    assert not before.passed
    assert (
        "scripts:inventory"
        in before.failed
    )

    repaired = broken.apply(
        lab.canonical_repair(
            broken,
            before,
        )
    )

    assert (
        rogue_path
        not in repaired.tree.files
    )
    assert lab.evaluate(
        repaired
    ).passed



def test_physics_fix_cannot_hitchhike_script_regression() -> None:
    lab = ExecutableGameProjectLab()
    project = lab.create(
        EngineEra.HD
    )
    physics_manifest_path = (
        "physics/compiled/manifest.json"
    )
    physics_manifest = json.loads(
        project.tree.read(
            physics_manifest_path
        )
    )
    physics_manifest[
        "manifest_digest"
    ] = "0" * 64
    broken = project.apply(
        (
            SandboxPatch(
                physics_manifest_path,
                json.dumps(
                    physics_manifest
                ),
                project.tree.file_digest(
                    physics_manifest_path
                ),
            ),
        )
    )
    before = lab.evaluate(
        broken
    )
    assert before.runtime_score == 1.0
    assert before.asset_score == 1.0
    assert before.script_score == 1.0
    assert before.physics_score < 1.0

    physics_repair = tuple(
        patch
        for patch
        in lab.canonical_repair(
            broken,
            before,
        )
        if patch.path.startswith(
            "physics/compiled/"
        )
    )
    script_manifest_path = (
        "scripts/compiled/manifest.json"
    )
    script_manifest = json.loads(
        broken.tree.read(
            script_manifest_path
        )
    )
    script_manifest["script_count"] += 1
    script_poison = SandboxPatch(
        script_manifest_path,
        json.dumps(
            script_manifest
        ),
        broken.tree.file_digest(
            script_manifest_path
        ),
    )

    evolution = AdversarialGameProjectEvolution(
        lab
    )
    session = evolution.start(
        broken
    )
    (
        next_session,
        report,
        round_result,
    ) = evolution.tournament_round(
        session,
        (
            physics_repair
            + (script_poison,),
        ),
    )

    assert not round_result.accepted
    assert report == before
    assert (
        next_session.sandbox.tree.digest
        == broken.tree.digest
    )


def test_project_physics_recipe_is_frozen_within_lineage() -> None:
    lab = ExecutableGameProjectLab()
    project = lab.create(
        EngineEra.MODERN
    )
    session = ProjectEvolutionSession.start(
        project
    )
    different_physics = PhysicsSceneSource(
        bounds=project.physics.bounds,
        gravity=Vec3(
            0.0,
            0.0,
            0.0,
        ),
        bodies=project.physics.bodies,
        constraints=
            project.physics.constraints,
    )
    different = lab.create(
        EngineEra.MODERN,
        physics=different_physics,
    )

    with pytest.raises(
        GameEngineLabError,
        match="physics recipe",
    ):
        session.checkpoint(
            different
        )


def test_untracked_compiled_physics_is_removed_by_project_repair() -> None:
    lab = ExecutableGameProjectLab()
    project = lab.create(
        EngineEra.OPEN_WORLD
    )
    rogue_path = (
        "physics/compiled/"
        "untracked.json"
    )
    broken = project.apply(
        (
            SandboxPatch(
                rogue_path,
                "{}",
            ),
        )
    )

    before = lab.evaluate(
        broken
    )
    assert not before.passed
    assert (
        "physics:inventory"
        in before.failed
    )

    repaired = broken.apply(
        lab.canonical_repair(
            broken,
            before,
        )
    )

    assert (
        rogue_path
        not in repaired.tree.files
    )
    assert lab.evaluate(
        repaired
    ).passed



def test_audio_fix_cannot_hitchhike_physics_regression() -> None:
    lab = ExecutableGameProjectLab()
    project = lab.create(
        EngineEra.MODERN
    )
    audio_manifest_path = (
        "audio/compiled/manifest.json"
    )
    audio_manifest = json.loads(
        project.tree.read(
            audio_manifest_path
        )
    )
    audio_manifest[
        "manifest_digest"
    ] = "0" * 64
    broken = project.apply(
        (
            SandboxPatch(
                audio_manifest_path,
                json.dumps(
                    audio_manifest
                ),
                project.tree.file_digest(
                    audio_manifest_path
                ),
            ),
        )
    )
    before = lab.evaluate(
        broken
    )
    assert before.runtime_score == 1.0
    assert before.asset_score == 1.0
    assert before.script_score == 1.0
    assert before.physics_score == 1.0
    assert before.audio_score < 1.0

    audio_repair = tuple(
        patch
        for patch
        in lab.canonical_repair(
            broken,
            before,
        )
        if patch.path.startswith(
            "audio/compiled/"
        )
    )
    physics_manifest_path = (
        "physics/compiled/manifest.json"
    )
    physics_manifest = json.loads(
        broken.tree.read(
            physics_manifest_path
        )
    )
    physics_manifest[
        "manifest_digest"
    ] = "f" * 64
    physics_poison = SandboxPatch(
        physics_manifest_path,
        json.dumps(
            physics_manifest
        ),
        broken.tree.file_digest(
            physics_manifest_path
        ),
    )

    evolution = AdversarialGameProjectEvolution(
        lab
    )
    session = evolution.start(
        broken
    )
    (
        next_session,
        report,
        round_result,
    ) = evolution.tournament_round(
        session,
        (
            audio_repair
            + (physics_poison,),
        ),
    )

    assert not round_result.accepted
    assert report == before
    assert (
        next_session.sandbox.tree.digest
        == broken.tree.digest
    )


def test_project_audio_recipe_is_frozen_within_lineage() -> None:
    lab = ExecutableGameProjectLab()
    project = lab.create(
        EngineEra.OPEN_WORLD
    )
    session = ProjectEvolutionSession.start(
        project
    )
    different_audio = AudioSceneSource(
        listener=AudioPosition(
            3.0,
            0.0,
            0.0,
        ),
        sounds=project.audio.sounds,
    )
    different = lab.create(
        EngineEra.OPEN_WORLD,
        audio=different_audio,
    )

    with pytest.raises(
        GameEngineLabError,
        match="audio recipe",
    ):
        session.checkpoint(
            different
        )


def test_untracked_compiled_audio_is_removed_by_project_repair() -> None:
    lab = ExecutableGameProjectLab()
    project = lab.create(
        EngineEra.NEXT
    )
    rogue_path = (
        "audio/compiled/"
        "untracked.json"
    )
    broken = project.apply(
        (
            SandboxPatch(
                rogue_path,
                "{}",
            ),
        )
    )

    before = lab.evaluate(
        broken
    )
    assert not before.passed
    assert (
        "audio:inventory"
        in before.failed
    )

    repaired = broken.apply(
        lab.canonical_repair(
            broken,
            before,
        )
    )

    assert (
        rogue_path
        not in repaired.tree.files
    )
    assert lab.evaluate(
        repaired
    ).passed



def test_animation_fix_cannot_hitchhike_audio_regression() -> None:
    lab = ExecutableGameProjectLab()
    project = lab.create(
        EngineEra.MODERN
    )
    animation_manifest_path = (
        "animation/compiled/manifest.json"
    )
    animation_manifest = json.loads(
        project.tree.read(
            animation_manifest_path
        )
    )
    animation_manifest[
        "manifest_digest"
    ] = "0" * 64
    broken = project.apply(
        (
            SandboxPatch(
                animation_manifest_path,
                json.dumps(
                    animation_manifest
                ),
                project.tree.file_digest(
                    animation_manifest_path
                ),
            ),
        )
    )
    before = lab.evaluate(
        broken
    )
    assert before.runtime_score == 1.0
    assert before.asset_score == 1.0
    assert before.script_score == 1.0
    assert before.physics_score == 1.0
    assert before.audio_score == 1.0
    assert before.animation_score < 1.0

    animation_repair = tuple(
        patch
        for patch
        in lab.canonical_repair(
            broken,
            before,
        )
        if patch.path.startswith(
            "animation/compiled/"
        )
    )
    audio_manifest_path = (
        "audio/compiled/manifest.json"
    )
    audio_manifest = json.loads(
        broken.tree.read(
            audio_manifest_path
        )
    )
    audio_manifest[
        "manifest_digest"
    ] = "f" * 64
    audio_poison = SandboxPatch(
        audio_manifest_path,
        json.dumps(
            audio_manifest
        ),
        broken.tree.file_digest(
            audio_manifest_path
        ),
    )

    evolution = AdversarialGameProjectEvolution(
        lab
    )
    session = evolution.start(
        broken
    )
    (
        next_session,
        report,
        round_result,
    ) = evolution.tournament_round(
        session,
        (
            animation_repair
            + (audio_poison,),
        ),
    )

    assert not round_result.accepted
    assert report == before
    assert (
        next_session.sandbox.tree.digest
        == broken.tree.digest
    )


def test_project_animation_recipe_is_frozen_within_lineage() -> None:
    lab = ExecutableGameProjectLab()
    project = lab.create(
        EngineEra.HD
    )
    session = ProjectEvolutionSession.start(
        project
    )
    different_animation = AnimationSceneSource(
        clips=(
            project.animation.clips[1],
            project.animation.clips[0],
        ),
    )
    different = lab.create(
        EngineEra.HD,
        animation=different_animation,
    )

    with pytest.raises(
        GameEngineLabError,
        match="animation recipe",
    ):
        session.checkpoint(
            different
        )


def test_untracked_compiled_animation_is_removed_by_project_repair() -> None:
    lab = ExecutableGameProjectLab()
    project = lab.create(
        EngineEra.NEXT
    )
    rogue_path = (
        "animation/compiled/"
        "untracked.clip.json"
    )
    broken = project.apply(
        (
            SandboxPatch(
                rogue_path,
                "{}",
            ),
        )
    )

    before = lab.evaluate(
        broken
    )
    assert not before.passed
    assert (
        "animation:inventory"
        in before.failed
    )

    repaired = broken.apply(
        lab.canonical_repair(
            broken,
            before,
        )
    )

    assert (
        rogue_path
        not in repaired.tree.files
    )
    assert lab.evaluate(
        repaired
    ).passed



def test_project_evolution_promotes_canonical_cleanup_of_rogue_runtime_file() -> None:
    lab = ExecutableGameProjectLab()
    project = lab.create(
        EngineEra.MODERN
    )
    rogue_path = (
        "notes/unattested.txt"
    )
    broken = project.apply(
        (
            SandboxPatch(
                rogue_path,
                "rogue",
            ),
        )
    )
    before = lab.evaluate(
        broken
    )

    assert not before.passed
    assert "runtime:contract" in before.failed
    assert (
        rogue_path
        in before.runtime.contract_mismatches
    )

    evolution = AdversarialGameProjectEvolution(
        lab
    )
    session = evolution.start(
        broken
    )
    candidates = (
        evolution.canonical_candidates(
            session,
            before,
        )
    )

    assert candidates
    assert any(
        patch.path == rogue_path
        and patch.content is None
        for patch
        in candidates[0]
    )

    (
        promoted,
        report,
        round_result,
    ) = evolution.tournament_round(
        session,
        candidates,
    )

    assert round_result.accepted
    assert report.passed
    assert (
        rogue_path
        not in promoted.sandbox.tree.files
    )
