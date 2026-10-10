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


def test_gb_tone_decoder_rounds_and_refuses_reserved_bits():
    assert abs(gameboy_pulse_frequency(gameboy_pulse_period(523))-523)<3
    assert gameboy_pulse_frequency(0)==64.0
    with pytest.raises(AudioKernelError):
        gameboy_pulse_frequency(2048)


def test_nes_pulse_apu_timer_and_valid_frequency():
    timer=nes_pulse_timer(440)
    assert 0 <= timer <= 2047
    assert abs(1789773/(16*(timer+1))-440)<2
    with pytest.raises(AudioKernelError):
        nes_pulse_timer(-1)


def test_sn76489_period_is_bounded_and_recoverable():
    timer=sn76489_tone_period(440)
    assert 1<=timer<=1023
    assert abs(3579545/(32*timer)-440)<3
    with pytest.raises(AudioKernelError):
        sn76489_tone_period(440,master_clock=True)


def test_ay38910_psg_12bit_tone_range():
    period=ay38910_tone_period(440)
    assert 1<=period<=4095
    assert abs(1773400/(16*period)-440)<3
    with pytest.raises(AudioKernelError):
        ay38910_tone_period(0)


def test_pulse_pcm_duty_phase_and_sampling_bounds():
    pcm=pulse_pcm(1000,8000,8)
    assert pcm==(32767,)*4+(-32767,)*4
    assert pulse_pcm(1000,8000,16)[:8]==pcm
    with pytest.raises(AudioKernelError):
        pulse_pcm(6000,8000,8)
    with pytest.raises(AudioKernelError):
        pulse_pcm(100,8000,8,duty_num=2,duty_den=2)

