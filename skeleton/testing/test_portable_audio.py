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


def test_triangle_pcm_has_symmetric_ramp_and_clamped_amplitude():
    a=triangle_pcm(1000,8000,16)
    assert a[0]==-32767 and a[4]==32767 and a[8]==-32767
    assert min(a)>=-32767 and max(a)<=32767
    with pytest.raises(AudioKernelError):
        triangle_pcm(4001,8000,8)


def test_lfsr_noise_replays_seed_without_unbounded_state():
    first=noise_lfsr_pcm(1,256)
    assert first==noise_lfsr_pcm(1,256)
    assert first!=noise_lfsr_pcm(2,256)
    assert set(first)=={-32767,32767}
    with pytest.raises(AudioKernelError):
        noise_lfsr_pcm(0,1)

def test_adsr_envelope_respects_phase_lengths_and_release_zero():
    env=adsr_envelope(10,attack=2,decay=2,sustain=16384,release=2)
    assert env[0]<env[1]==32767
    assert env[3]==16384
    assert env[5]==16384 and env[-1]==0
    with pytest.raises(AudioKernelError):
        adsr_envelope(4,attack=2,decay=2,sustain=1000,release=1)

def test_resampling_preserves_bounded_pcm_and_integer_midpoints():
    assert resample_linear((0,1000,0,-1000),8000,16000)[:4]==(0,500,1000,500)
    assert len(resample_linear((0,1000,0,-1000),16000,8000))==2
    assert resample_linear((-32768,),8000,16000)==(-32768,-32768)
    with pytest.raises(AudioKernelError):
        resample_linear((0,)*32768,4000,96000)
