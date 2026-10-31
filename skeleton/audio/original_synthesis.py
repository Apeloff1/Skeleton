"""Original offline sound-effect synthesis with deterministic fixed-point PCM.

This is a bounded asset-production adapter owned by the existing audio plane.
It does not synthesize speech, licensed music, or real-time spatial audio.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
import wave

from skeleton.audio.pipeline import AudioAsset, AudioError, AudioLimits

PHASE_BITS = 32
PHASE_MOD = 1 << PHASE_BITS
MAX_SAMPLES = 1_440_000
MAX_WAV_BYTES = 3_000_000
SAMPLE_RATES = (8000, 16000, 22050, 44100, 48000)
WAVEFORMS = ("square", "triangle", "saw", "noise")


def _integer(value: object, lower: int, upper: int, field: str) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise AudioError(f"invalid {field}")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not 3 <= len(value) <= 128 or value != value.strip():
        raise AudioError(f"invalid {field}")
    return value


@dataclass(frozen=True, slots=True)
class SoundPatch:
    """Versioned, original, portable sound effect instructions."""

    patch_id: str
    author: str
    license: str
    waveform: str
    sample_rate: int
    frequency_millihz: int
    duration_ms: int
    gain_permille: int
    attack_ms: int
    release_ms: int
    seed: int

    @classmethod
    def from_mapping(cls, source: object) -> "SoundPatch":
        fields = {
            "version", "patch_id", "author", "license", "waveform", "sample_rate",
            "frequency_millihz", "duration_ms", "gain_permille",
            "attack_ms", "release_ms", "seed",
        }
        if not isinstance(source, dict) or set(source) != fields:
            raise AudioError("invalid patch fields")
        if type(source["version"]) is not int or source["version"] != 1:
            raise AudioError("unsupported sound patch version")
        patch_id = _text(source["patch_id"], "patch_id")
        if not patch_id.startswith("SFX."):
            raise AudioError("sound patch ID must begin SFX.")
        author = _text(source["author"], "author")
        if source["license"] != "CC0-1.0":
            raise AudioError("original CC0 sound patch required")
        if source["waveform"] not in WAVEFORMS:
            raise AudioError("unsupported waveform")
        sample_rate = _integer(source["sample_rate"], 8000, 48000, "sample_rate")
        if sample_rate not in SAMPLE_RATES:
            raise AudioError("unsupported sample_rate")
        frequency = _integer(source["frequency_millihz"], 1000, 20_000_000, "frequency_millihz")
        if frequency * 2 > sample_rate * 1000:
            raise AudioError("frequency above Nyquist")
        duration = _integer(source["duration_ms"], 1, 30000, "duration_ms")
        gain = _integer(source["gain_permille"], 0, 1000, "gain_permille")
        attack = _integer(source["attack_ms"], 0, duration, "attack_ms")
        release = _integer(source["release_ms"], 0, duration, "release_ms")
        if attack + release > duration:
            raise AudioError("envelope exceeds duration")
        seed = _integer(source["seed"], 1, 0xFFFFFFFF, "seed")
        if sample_rate * duration // 1000 > MAX_SAMPLES:
            raise AudioError("sound exceeds sample budget")
        return cls(patch_id, author, "CC0-1.0", source["waveform"], sample_rate,
                   frequency, duration, gain, attack, release, seed)

    def manifest(self) -> dict:
        return {
            "version": 1, "patch_id": self.patch_id, "author": self.author,
            "license": self.license, "waveform": self.waveform,
            "sample_rate": self.sample_rate, "frequency_millihz": self.frequency_millihz,
            "duration_ms": self.duration_ms, "gain_permille": self.gain_permille,
            "attack_ms": self.attack_ms, "release_ms": self.release_ms, "seed": self.seed,
        }

    @property
    def source_digest(self) -> str:
        raw = json.dumps(self.manifest(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class RenderedSound:
    patch: SoundPatch
    wav_bytes: bytes
    asset: AudioAsset
    wav_digest: str

    def receipt(self) -> dict:
        return {
            "schema_version": 1, "patch_id": self.patch.patch_id,
            "source_digest": self.patch.source_digest, "wav_sha256": self.wav_digest,
            "sample_rate": self.asset.sample_rate, "channels": 1,
            "duration_ms": self.patch.duration_ms, "encoded_bytes": len(self.wav_bytes),
            "license": self.patch.license, "author": self.patch.author,
            "format": "pcm_s16le_wav",
        }


def _wave_sample(waveform: str, phase: int, noise_state: int) -> tuple[int, int]:
    if waveform == "square":
        return (32767 if phase < PHASE_MOD // 2 else -32768), noise_state
    if waveform == "triangle":
        value = 32767 - (abs(phase - PHASE_MOD // 2) * 65535 // (PHASE_MOD // 2))
        return value, noise_state
    if waveform == "saw":
        return (phase * 65535 // PHASE_MOD) - 32768, noise_state
    # Xorshift32 is deterministic, not a cryptographic random generator.
    noise_state ^= (noise_state << 13) & 0xFFFFFFFF
    noise_state ^= noise_state >> 17
    noise_state ^= (noise_state << 5) & 0xFFFFFFFF
    noise_state &= 0xFFFFFFFF
    return (noise_state & 0xFFFF) - 32768, noise_state


def synthesize(patch: SoundPatch) -> RenderedSound:
    """Render bounded 16-bit mono WAV, with no disk/network side effects."""

    # Revalidate reconstructed or subclassed patch values at the trust boundary.
    patch = SoundPatch.from_mapping(patch.manifest())
    count = patch.sample_rate * patch.duration_ms // 1000
    if not 1 <= count <= MAX_SAMPLES:
        raise AudioError("invalid frame budget")
    attack_frames = patch.sample_rate * patch.attack_ms // 1000
    release_frames = patch.sample_rate * patch.release_ms // 1000
    step = patch.frequency_millihz * PHASE_MOD // (patch.sample_rate * 1000)
    phase = 0
    noise_state = patch.seed
    frames = bytearray(count * 2)
    for index in range(count):
        value, noise_state = _wave_sample(patch.waveform, phase, noise_state)
        phase = (phase + step) & 0xFFFFFFFF
        envelope = 1000
        if attack_frames:
            envelope = min(envelope, index * 1000 // attack_frames)
        if release_frames:
            envelope = min(envelope, (count - 1 - index) * 1000 // release_frames)
        scaled = value * patch.gain_permille * envelope // 1_000_000
        frames[index * 2:index * 2 + 2] = int(scaled).to_bytes(2, "little", signed=True)
    output = BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(patch.sample_rate)
        writer.writeframes(frames)
    encoded = output.getvalue()
    if len(encoded) > MAX_WAV_BYTES:
        raise AudioError("encoded audio exceeds budget")
    asset = AudioAsset(patch.patch_id, patch.source_digest, patch.sample_rate, 1,
                       patch.duration_ms, len(encoded))
    AudioLimits(30000, 1, 48000, MAX_WAV_BYTES).admit(asset)
    return RenderedSound(patch, encoded, asset, sha256(encoded).hexdigest())
