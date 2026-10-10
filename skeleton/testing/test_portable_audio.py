"""Reproducible PSG timer and bounded PCM synthesis regressions."""
import pytest
from skeleton.ai.game_builder.portable_kernels.audio import (
    AudioKernelError, gameboy_pulse_period, gameboy_pulse_frequency,
    nes_pulse_timer, sn76489_tone_period, ay38910_tone_period, pulse_pcm,
    triangle_pcm, noise_lfsr_pcm, adsr_envelope, resample_linear,
)


def test_gb_tone_pitch_admission_and_11bit_period():
    period=gameboy_pulse_period(440)
    assert 0 <= period < 2048
    assert abs(131072/(2048-period)-440)<2
    with pytest.raises(AudioKernelError):
        gameboy_pulse_period(0)

