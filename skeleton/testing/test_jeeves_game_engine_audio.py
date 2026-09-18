from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.jeeves.core import Jeeves
from skeleton.jeeves.game_engine_audio import (
    AUDIO_POLICIES,
    AudioAdversary,
    AudioPosition,
    AudioSceneSource,
    HistoricalAudioMixer,
    SoundRecipe,
    SpatialMode,
    Waveform,
    attach_audio_build,
    audio_policy,
    canonical_audio_patches,
    canonical_audio_source,
    compile_audio_build,
)
from skeleton.jeeves.game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    SandboxPatch,
)
from skeleton.jeeves.game_engine_runtime import (
    ExecutableGameEngineLab,
)


@pytest.mark.parametrize(
    "era",
    list(EngineEra),
)
def test_every_era_has_audio_policy(
    era: EngineEra,
) -> None:
    assert era in AUDIO_POLICIES
    assert audio_policy(era).era is era


@pytest.mark.parametrize(
    "era",
    list(EngineEra),
)
def test_canonical_audio_build_is_deterministic_and_passes_adversary(
    era: EngineEra,
) -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        era,
        "action_adventure",
    )
    source = canonical_audio_source(
        era
    )

    first = compile_audio_build(
        era,
        source,
    )
    second = compile_audio_build(
        era,
        source,
    )

    assert first == second
    assert len(first.source_digest) == 64
    assert len(first.policy_digest) == 64
    assert len(first.manifest_digest) == 64

    attached = attach_audio_build(
        sandbox,
        source,
    )
    report = AudioAdversary().evaluate(
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
        "voice_budget",
        "spatial",
    } == {
        probe.name
        for probe in report.probes
    }


def test_audio_capabilities_progress_with_engine_eras() -> None:
    pong = audio_policy(
        EngineEra.PONG
    )
    eight = audio_policy(
        EngineEra.EIGHT_BIT
    )
    sixteen = audio_policy(
        EngineEra.SIXTEEN_BIT
    )
    fixed = audio_policy(
        EngineEra.FIXED_3D
    )
    hd = audio_policy(
        EngineEra.HD
    )
    modern = audio_policy(
        EngineEra.MODERN
    )
    nxt = audio_policy(
        EngineEra.NEXT
    )

    assert pong.max_voices == 1
    assert pong.output_channels == 1
    assert (
        pong.spatial_mode
        is SpatialMode.MONO
    )
    assert Waveform.PCM in eight.waveforms
    assert sixteen.output_channels == 2
    assert (
        sixteen.spatial_mode
        is SpatialMode.PAN
    )
    assert fixed.streaming
    assert (
        fixed.spatial_mode
        is SpatialMode.DISTANCE
    )
    assert hd.output_channels == 6
    assert (
        modern.spatial_mode
        is SpatialMode.OBJECT
    )
    assert modern.max_voices == 256
    assert nxt.max_voices == 512
    assert nxt.sample_rate == 192_000


def test_pong_rejects_later_waveform() -> None:
    source = AudioSceneSource(
        AudioPosition(),
        (
            SoundRecipe(
                "sample",
                Waveform.PCM,
                220.0,
                0.5,
                5,
            ),
        ),
    )

    with pytest.raises(
        GameEngineLabError,
        match="unavailable",
    ):
        compile_audio_build(
            EngineEra.PONG,
            source,
        )


def test_mono_era_rejects_pan() -> None:
    source = AudioSceneSource(
        AudioPosition(),
        (
            SoundRecipe(
                "panned",
                Waveform.SQUARE,
                440.0,
                0.5,
                5,
                pan=0.5,
            ),
        ),
    )

    with pytest.raises(
        GameEngineLabError,
        match="pan unavailable",
    ):
        compile_audio_build(
            EngineEra.PONG,
            source,
        )


def test_pong_voice_budget_rejects_second_concurrent_sound() -> None:
    mixer = HistoricalAudioMixer(
        EngineEra.PONG
    )
    first = SoundRecipe(
        "first",
        Waveform.SQUARE,
        440.0,
        0.4,
        10,
    )
    second = SoundRecipe(
        "second",
        Waveform.SQUARE,
        660.0,
        0.4,
        10,
    )

    frame = mixer.mix_tick(
        (
            first,
            second,
        )
    )

    assert len(mixer.voices) == 1
    assert len(frame.started) == 1
    assert len(frame.rejected) == 1
    assert frame.stolen == ()


def test_arcade_voice_stealing_is_priority_deterministic() -> None:
    policy = audio_policy(
        EngineEra.ARCADE
    )
    mixer = HistoricalAudioMixer(
        EngineEra.ARCADE
    )
    initial = tuple(
        SoundRecipe(
            f"voice_{index}",
            Waveform.SQUARE,
            220.0 + index,
            0.1,
            20,
            priority=index,
        )
        for index in range(
            policy.max_voices
        )
    )
    mixer.mix_tick(initial)
    replacement = SoundRecipe(
        "urgent",
        Waveform.SQUARE,
        880.0,
        0.2,
        20,
        priority=127,
    )

    frame = mixer.mix_tick(
        (replacement,)
    )

    assert len(mixer.voices) == (
        policy.max_voices
    )
    assert frame.stolen == (
        "voice_0",
    )
    assert "urgent" in (
        voice.sound_id
        for voice in mixer.voices
    )


def test_stereo_pan_produces_asymmetric_channels() -> None:
    mixer = HistoricalAudioMixer(
        EngineEra.SIXTEEN_BIT
    )
    sound = SoundRecipe(
        "right",
        Waveform.PCM,
        440.0,
        0.8,
        5,
        pan=0.8,
    )

    frame = mixer.mix_tick(
        (sound,)
    )

    assert len(frame.channels) == 2
    assert (
        frame.channels[1]
        > frame.channels[0]
    )


def test_distance_spatialization_attenuates_far_voice() -> None:
    policy = audio_policy(
        EngineEra.FIXED_3D
    )
    near_mixer = HistoricalAudioMixer(
        EngineEra.FIXED_3D
    )
    far_mixer = HistoricalAudioMixer(
        EngineEra.FIXED_3D
    )
    near = SoundRecipe(
        "tone",
        Waveform.PCM,
        440.0,
        0.8,
        5,
        position=AudioPosition(
            1.0,
            0.0,
            0.0,
        ),
    )
    far = replace(
        near,
        position=AudioPosition(
            policy.max_distance,
            0.0,
            0.0,
        ),
    )

    near_frame = near_mixer.mix_tick(
        (near,)
    )
    far_frame = far_mixer.mix_tick(
        (far,)
    )

    assert (
        sum(near_frame.channels)
        > sum(far_frame.channels)
    )


def test_hd_surround_and_modern_object_mix_have_expected_channel_counts() -> None:
    for era, expected in (
        (
            EngineEra.HD,
            6,
        ),
        (
            EngineEra.MODERN,
            8,
        ),
    ):
        policy = audio_policy(era)
        mixer = HistoricalAudioMixer(
            era
        )
        sound = SoundRecipe(
            "spatial",
            policy.waveforms[0],
            440.0,
            0.4,
            5,
            pan=0.3,
            position=AudioPosition(
                10.0,
                0.0,
                -20.0,
            ),
        )

        frame = mixer.mix_tick(
            (sound,)
        )

        assert (
            len(frame.channels)
            == expected
        )
        assert len(
            set(frame.channels)
        ) > 1


def test_audio_replay_is_deterministic() -> None:
    source = canonical_audio_source(
        EngineEra.MODERN
    )

    def run():
        mixer = HistoricalAudioMixer(
            EngineEra.MODERN,
            listener=source.listener,
        )
        schedule = {
            0: source.sounds,
            12: (
                source.sounds[0],
            ),
        }
        return (
            mixer.run(
                schedule,
                60,
            ),
            mixer.fingerprint(),
        )

    assert run() == run()


def test_audio_snapshot_restore_recovers_voice_state() -> None:
    source = canonical_audio_source(
        EngineEra.HD
    )
    mixer = HistoricalAudioMixer(
        EngineEra.HD
    )
    mixer.mix_tick(
        source.sounds
    )
    snapshot = mixer.snapshot()
    before = mixer.fingerprint()

    mixer.run(
        {},
        5,
    )
    mixer.restore(
        snapshot
    )

    assert mixer.fingerprint() == before
    assert (
        mixer.tick
        == snapshot.tick
    )


def test_audio_snapshot_tamper_is_rejected() -> None:
    source = canonical_audio_source(
        EngineEra.MODERN
    )
    mixer = HistoricalAudioMixer(
        EngineEra.MODERN
    )
    mixer.mix_tick(
        source.sounds
    )
    snapshot = mixer.snapshot()
    forged = replace(
        snapshot,
        digest="0" * 64,
    )

    with pytest.raises(
        GameEngineLabError,
        match="digest mismatch",
    ):
        mixer.restore(forged)


def test_duplicate_sound_ids_fail_closed() -> None:
    sound = SoundRecipe(
        "same",
        Waveform.PCM,
        440.0,
        0.3,
        4,
    )
    source = AudioSceneSource(
        AudioPosition(),
        (
            sound,
            sound,
        ),
    )

    with pytest.raises(
        GameEngineLabError,
        match="unique",
    ):
        compile_audio_build(
            EngineEra.MODERN,
            source,
        )


def test_audio_manifest_tamper_is_detected_and_repaired() -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        EngineEra.MODERN
    )
    source = canonical_audio_source(
        EngineEra.MODERN
    )
    attached = attach_audio_build(
        sandbox,
        source,
    )
    path = (
        "audio/compiled/"
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

    before = AudioAdversary().evaluate(
        broken,
        source,
    )
    assert not before.passed
    assert "manifest" in before.failed

    repaired = broken.apply(
        canonical_audio_patches(
            broken,
            source,
        )
    )

    assert AudioAdversary().evaluate(
        repaired,
        source,
    ).passed


def test_untracked_compiled_audio_is_detected_and_removed() -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        EngineEra.NEXT
    )
    source = canonical_audio_source(
        EngineEra.NEXT
    )
    attached = attach_audio_build(
        sandbox,
        source,
    )
    rogue_path = (
        "audio/compiled/"
        "rogue.json"
    )
    broken = attached.apply(
        (
            SandboxPatch(
                rogue_path,
                "{}",
            ),
        )
    )

    report = AudioAdversary().evaluate(
        broken,
        source,
    )

    assert not report.passed
    assert "inventory" in report.failed

    repaired = broken.apply(
        canonical_audio_patches(
            broken,
            source,
        )
    )

    assert (
        rogue_path
        not in repaired.tree.files
    )
    assert AudioAdversary().evaluate(
        repaired,
        source,
    ).passed


def test_runtime_quality_accepts_attested_audio_plane() -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        EngineEra.OPEN_WORLD
    )
    source = canonical_audio_source(
        EngineEra.OPEN_WORLD
    )
    attached = attach_audio_build(
        sandbox,
        source,
    )

    assert lab.evaluate(
        attached
    ).passed



def test_jeeves_compiles_evaluates_and_simulates_historical_audio() -> None:
    jeeves = Jeeves()
    sandbox = jeeves.build_game_engine(
        EngineEra.HD,
        gameplay_dialect="immersive_sim",
    )
    source = canonical_audio_source(
        EngineEra.HD
    )

    compiled = jeeves.compile_game_audio(
        sandbox,
        source,
    )
    report = jeeves.evaluate_game_audio(
        compiled,
        source,
    )
    frames, mixer = jeeves.simulate_game_audio(
        compiled,
        source,
        ticks=24,
    )

    assert report.passed
    assert len(frames) == 24
    assert mixer.tick == 24
    assert len(
        mixer.fingerprint()
    ) == 64
    assert (
        jeeves.evaluate_game_engine(
            compiled
        ).passed
    )
