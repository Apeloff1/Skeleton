from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.jeeves.core import Jeeves
from skeleton.jeeves.game_engine_animation import (
    ANIMATION_POLICIES,
    AnimationAdversary,
    AnimationClipSource,
    AnimationKeyframe,
    AnimationSceneSource,
    AnimationTrack,
    HistoricalAnimator,
    Interpolation,
    TrackKind,
    animation_policy,
    attach_animation_build,
    canonical_animation_patches,
    canonical_animation_source,
    compile_animation_build,
    solve_two_bone_ik,
)
from skeleton.jeeves.game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    SandboxPatch,
)
from skeleton.jeeves.game_engine_runtime import (
    ExecutableGameEngineLab,
)


def _track(
    target: str,
    kind: TrackKind,
    interpolation: Interpolation,
    *points: tuple[int, float],
) -> AnimationTrack:
    return AnimationTrack(
        target,
        kind,
        interpolation,
        tuple(
            AnimationKeyframe(
                tick,
                value,
            )
            for tick, value
            in points
        ),
    )


@pytest.mark.parametrize(
    "era",
    list(EngineEra),
)
def test_every_era_has_animation_policy(
    era: EngineEra,
) -> None:
    assert era in ANIMATION_POLICIES
    assert animation_policy(era).era is era


@pytest.mark.parametrize(
    "era",
    list(EngineEra),
)
def test_canonical_animation_build_is_deterministic_and_passes_adversary(
    era: EngineEra,
) -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        era,
        "action_adventure",
    )
    source = canonical_animation_source(
        era
    )

    first = compile_animation_build(
        era,
        source,
    )
    second = compile_animation_build(
        era,
        source,
    )

    assert first == second
    assert len(first.policy_digest) == 64
    assert len(first.source_digest) == 64
    assert len(first.manifest_digest) == 64

    attached = attach_animation_build(
        sandbox,
        source,
    )
    report = AnimationAdversary().evaluate(
        attached,
        source,
    )

    assert report.passed
    assert report.score == 1.0
    assert {
        "manifest",
        "inventory",
        "integrity",
        "replay",
        "snapshot",
        "blend",
        "root_motion",
        "ik",
    } == {
        probe.name
        for probe in report.probes
    }


def test_animation_capabilities_progress_across_eras() -> None:
    pong = animation_policy(
        EngineEra.PONG
    )
    eight = animation_policy(
        EngineEra.EIGHT_BIT
    )
    sixteen = animation_policy(
        EngineEra.SIXTEEN_BIT
    )
    early = animation_policy(
        EngineEra.EARLY_3D
    )
    fixed = animation_policy(
        EngineEra.FIXED_3D
    )
    hd = animation_policy(
        EngineEra.HD
    )
    modern = animation_policy(
        EngineEra.MODERN
    )
    nxt = animation_policy(
        EngineEra.NEXT
    )

    assert pong.allowed_tracks == (
        TrackKind.SPRITE_INDEX,
    )
    assert not pong.blending
    assert (
        TrackKind.TRANSLATION_X
        in eight.allowed_tracks
    )
    assert sixteen.blending
    assert (
        TrackKind.TRANSLATION_Z
        in early.allowed_tracks
    )
    assert (
        TrackKind.BONE_ROTATION_DEG
        in fixed.allowed_tracks
    )
    assert fixed.max_bones == 32
    assert hd.root_motion
    assert (
        TrackKind.ROOT_X
        in hd.allowed_tracks
    )
    assert modern.ik
    assert (
        TrackKind.IK_WEIGHT
        in modern.allowed_tracks
    )
    assert (
        nxt.max_bones
        > modern.max_bones
    )


def test_pong_sprite_playback_is_discrete() -> None:
    source = canonical_animation_source(
        EngineEra.PONG
    )
    player = HistoricalAnimator(
        EngineEra.PONG,
        source,
    )

    values = [
        pose.values[0].value
        for pose
        in player.step(7)
    ]

    assert values == [
        0.0,
        0.0,
        0.0,
        1.0,
        1.0,
        1.0,
        0.0,
    ]


def test_eight_bit_linear_transform_interpolation() -> None:
    clip = AnimationClipSource(
        "move",
        10,
        False,
        (
            _track(
                "player",
                TrackKind.TRANSLATION_X,
                Interpolation.LINEAR,
                (0, 0.0),
                (10, 10.0),
            ),
        ),
    )
    player = HistoricalAnimator(
        EngineEra.EIGHT_BIT,
        AnimationSceneSource(
            (clip,)
        ),
    )

    pose = player.sample(
        tick=5.0
    )

    assert pose.values[0].value == 5.0


def test_smooth_interpolation_is_deterministic() -> None:
    clip = AnimationClipSource(
        "smooth",
        10,
        False,
        (
            _track(
                "player",
                TrackKind.TRANSLATION_X,
                Interpolation.SMOOTH,
                (0, 0.0),
                (10, 10.0),
            ),
        ),
    )
    source = AnimationSceneSource(
        (clip,)
    )

    left = HistoricalAnimator(
        EngineEra.SHADER,
        source,
    ).sample(tick=2.5)
    right = HistoricalAnimator(
        EngineEra.SHADER,
        source,
    ).sample(tick=2.5)

    assert left == right
    assert (
        left.values[0].value
        == pytest.approx(
            1.5625,
            abs=1e-6,
        )
    )


def test_blending_fails_closed_before_capability_era() -> None:
    source = canonical_animation_source(
        EngineEra.EIGHT_BIT
    )
    player = HistoricalAnimator(
        EngineEra.EIGHT_BIT,
        source,
    )

    with pytest.raises(
        GameEngineLabError,
        match="blending unavailable",
    ):
        player.blend(
            source.clips[0].clip_id,
            source.clips[1].clip_id,
            0.5,
        )


def test_sixteen_bit_blend_is_repeatable() -> None:
    source = canonical_animation_source(
        EngineEra.SIXTEEN_BIT
    )
    player = HistoricalAnimator(
        EngineEra.SIXTEEN_BIT,
        source,
    )

    first = player.blend(
        "idle",
        "move",
        0.25,
        tick=4,
    )
    second = player.blend(
        "idle",
        "move",
        0.25,
        tick=4,
    )

    assert first == second
    assert first.digest == second.digest


def test_root_motion_fails_closed_before_hd() -> None:
    source = canonical_animation_source(
        EngineEra.SHADER
    )
    player = HistoricalAnimator(
        EngineEra.SHADER,
        source,
    )

    with pytest.raises(
        GameEngineLabError,
        match="root motion unavailable",
    ):
        player.root_motion_delta(
            "move",
            0.0,
            4.0,
        )


def test_hd_root_motion_returns_deterministic_delta() -> None:
    source = canonical_animation_source(
        EngineEra.HD
    )
    player = HistoricalAnimator(
        EngineEra.HD,
        source,
    )

    first = player.root_motion_delta(
        "move",
        0.0,
        4.0,
    )
    second = player.root_motion_delta(
        "move",
        0.0,
        4.0,
    )

    assert first == second
    assert first[0] > 0
    assert first[1] > 0


def test_two_bone_ik_fails_closed_before_modern() -> None:
    with pytest.raises(
        GameEngineLabError,
        match="IK unavailable",
    ):
        solve_two_bone_ik(
            EngineEra.HD,
            root_x=0.0,
            root_y=0.0,
            target_x=1.0,
            target_y=1.0,
            upper_length=1.0,
            lower_length=1.0,
        )


@pytest.mark.parametrize(
    "era",
    [
        EngineEra.MODERN,
        EngineEra.NEXT,
    ],
)
def test_two_bone_ik_hits_reachable_target_deterministically(
    era: EngineEra,
) -> None:
    first = solve_two_bone_ik(
        era,
        root_x=0.0,
        root_y=0.0,
        target_x=1.0,
        target_y=1.0,
        upper_length=1.0,
        lower_length=1.0,
    )
    second = solve_two_bone_ik(
        era,
        root_x=0.0,
        root_y=0.0,
        target_x=1.0,
        target_y=1.0,
        upper_length=1.0,
        lower_length=1.0,
    )

    assert first == second
    assert first.reached
    assert first.end_x == pytest.approx(
        1.0
    )
    assert first.end_y == pytest.approx(
        1.0
    )


def test_two_bone_ik_clamps_unreachable_target() -> None:
    result = solve_two_bone_ik(
        EngineEra.MODERN,
        root_x=0.0,
        root_y=0.0,
        target_x=10.0,
        target_y=0.0,
        upper_length=1.0,
        lower_length=1.0,
    )

    assert not result.reached
    assert result.end_x == pytest.approx(
        2.0
    )
    assert result.end_y == pytest.approx(
        0.0
    )


def test_animator_snapshot_restore_recovers_playback_identity() -> None:
    source = canonical_animation_source(
        EngineEra.MODERN
    )
    player = HistoricalAnimator(
        EngineEra.MODERN,
        source,
    )
    player.play(
        "move",
        playback_rate=0.5,
    )
    player.step(13)
    snapshot = player.snapshot()
    before = player.fingerprint()

    player.step(9)
    player.restore(
        snapshot
    )

    assert player.fingerprint() == before
    assert (
        player.absolute_tick
        == snapshot.absolute_tick
    )


def test_animator_snapshot_tamper_is_rejected() -> None:
    source = canonical_animation_source(
        EngineEra.SHADER
    )
    player = HistoricalAnimator(
        EngineEra.SHADER,
        source,
    )
    player.step(3)
    snapshot = player.snapshot()
    forged = replace(
        snapshot,
        digest="0" * 64,
    )

    with pytest.raises(
        GameEngineLabError,
        match="digest mismatch",
    ):
        player.restore(
            forged
        )


def test_compile_rejects_duplicate_clip_ids() -> None:
    clip = canonical_animation_source(
        EngineEra.PONG
    ).clips[0]
    source = AnimationSceneSource(
        (
            clip,
            clip,
        )
    )

    with pytest.raises(
        GameEngineLabError,
        match="clip ids",
    ):
        compile_animation_build(
            EngineEra.PONG,
            source,
        )


def test_compile_rejects_skeletal_track_before_fixed_3d() -> None:
    clip = AnimationClipSource(
        "bad",
        4,
        False,
        (
            _track(
                "spine",
                TrackKind.BONE_ROTATION_DEG,
                Interpolation.LINEAR,
                (0, 0.0),
                (4, 10.0),
            ),
        ),
    )

    with pytest.raises(
        GameEngineLabError,
        match="unavailable",
    ):
        compile_animation_build(
            EngineEra.EARLY_3D,
            AnimationSceneSource(
                (clip,)
            ),
        )


def test_animation_manifest_tamper_is_detected_and_repaired() -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        EngineEra.HD
    )
    source = canonical_animation_source(
        EngineEra.HD
    )
    attached = attach_animation_build(
        sandbox,
        source,
    )
    path = (
        "animation/compiled/"
        "manifest.json"
    )
    broken = attached.apply(
        (
            SandboxPatch(
                path,
                "{}",
                attached.tree.file_digest(
                    path
                ),
            ),
        )
    )

    before = AnimationAdversary().evaluate(
        broken,
        source,
    )
    assert not before.passed
    assert "manifest" in before.failed

    repaired = broken.apply(
        canonical_animation_patches(
            broken,
            source,
        )
    )

    assert AnimationAdversary().evaluate(
        repaired,
        source,
    ).passed


def test_untracked_compiled_animation_is_detected_and_removed() -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        EngineEra.NEXT
    )
    source = canonical_animation_source(
        EngineEra.NEXT
    )
    attached = attach_animation_build(
        sandbox,
        source,
    )
    rogue = (
        "animation/compiled/"
        "rogue.clip.json"
    )
    broken = attached.apply(
        (
            SandboxPatch(
                rogue,
                "{}",
            ),
        )
    )

    report = AnimationAdversary().evaluate(
        broken,
        source,
    )
    assert not report.passed
    assert "inventory" in report.failed

    repaired = broken.apply(
        canonical_animation_patches(
            broken,
            source,
        )
    )

    assert (
        rogue
        not in repaired.tree.files
    )
    assert AnimationAdversary().evaluate(
        repaired,
        source,
    ).passed


def test_runtime_quality_accepts_attested_animation_plane() -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        EngineEra.MODERN
    )
    attached = attach_animation_build(
        sandbox,
        canonical_animation_source(
            EngineEra.MODERN
        ),
    )

    assert lab.evaluate(
        attached
    ).passed



def test_jeeves_compiles_evaluates_and_simulates_historical_animation() -> None:
    jeeves = Jeeves()
    sandbox = jeeves.build_game_engine(
        EngineEra.MODERN,
        gameplay_dialect="action_adventure",
    )
    source = canonical_animation_source(
        EngineEra.MODERN
    )

    compiled = jeeves.compile_game_animation(
        sandbox,
        source,
    )
    report = jeeves.evaluate_game_animation(
        compiled,
        source,
    )
    poses, animator = (
        jeeves.simulate_game_animation(
            compiled,
            source,
            clip_id="move",
            steps=24,
            playback_rate=0.5,
        )
    )

    assert report.passed
    assert len(poses) == 24
    assert animator.absolute_tick == 24
    assert len(
        animator.fingerprint()
    ) == 64
    assert (
        jeeves.evaluate_game_engine(
            compiled
        ).passed
    )



def test_fractional_playback_snapshot_is_stable_at_integral_float_tick() -> None:
    source = canonical_animation_source(
        EngineEra.MODERN
    )
    player = HistoricalAnimator(
        EngineEra.MODERN,
        source,
    )
    player.play(
        "move",
        playback_rate=0.5,
    )
    player.step(12)
    assert player.local_tick == 6.0

    snapshot = player.snapshot()
    before = player.fingerprint()
    player.step(3)
    player.restore(snapshot)

    assert snapshot.local_tick == 6.0
    assert player.fingerprint() == before
