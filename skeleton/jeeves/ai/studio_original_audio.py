"""Original, bounded deterministic WAV sound forge for the Jeeves game studio.

A model can propose a reviewed procedural sound document, but the host's
CreatorProjectSourceStore must first authorize and persist its exact contents.
The output is actual PCM-16 mono WAV with explicitly limited amplitudes and
durations. No external samples, licenses, networks, or synthesizer plug-ins are
implicitly imported. A separate verifier reconstructs every sample.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import re
import struct
from typing import Any

from .studio_interaction_contract import digest, identifier

SCHEMA = "skeleton.jeeves.original_audio_pcm.v1"
AUDIO_KEYS = frozenset((
    "kind", "asset_id", "waveform", "frequency_hz", "duration_ms",
    "attack_ms", "release_ms", "gain_per_mille", "seed", "sample_rate_hz",
))
WAVEFORMS = frozenset({"triangle", "square", "noise"})
SAMPLE_RATES = frozenset({8000, 16000, 22050, 44100})
ASSET_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
MAX_ASSETS = 64
MAX_SAMPLES = 132300  # 3 seconds at 44.1 kHz
MAX_WAV_BYTES = MAX_SAMPLES * 2 + 44


class OriginalAudioError(ValueError):
    """No safely reviewable original sound can be compiled from the source."""


def _number(value: Any, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise OriginalAudioError(name + " is outside the allowed original sound bounds")
    return value


def _validated_source(record: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    if not isinstance(record, Mapping) or record.get("facet") != "audio_forge":
        raise OriginalAudioError("original WAV source must belong to audio_forge")
    doc = record.get("document")
    if not isinstance(doc, dict) or set(doc) != AUDIO_KEYS:
        raise OriginalAudioError("original sound requires all reviewed synthesis parameters")
    if doc["kind"] != "procedural_pcm_sound":
        raise OriginalAudioError("unknown original audio source kind")
    record_id = identifier(record.get("record_id"), "audio source record")
    revision = _number(record.get("revision"), "source revision", 1, 1_000_000)
    dependencies = record.get("depends_on")
    if (type(dependencies) is not list or len(dependencies) > 32
            or any(type(item) is not str for item in dependencies)):
        raise OriginalAudioError("sound lacks exact durable source dependencies")
    expected = digest([record_id, "audio_forge", revision, doc, dependencies])
    if record.get("source_sha256") != expected:
        raise OriginalAudioError("sound is not bound to the persisted original revision")
    asset_id = doc["asset_id"]
    if type(asset_id) is not str or ASSET_ID.fullmatch(asset_id) is None:
        raise OriginalAudioError("sound asset name must be portable lowercase ASCII")
    if type(doc["waveform"]) is not str or doc["waveform"] not in WAVEFORMS:
        raise OriginalAudioError("sound waveform must use a reviewed oscillator")
    rate = doc["sample_rate_hz"]
    if type(rate) is not int or rate not in SAMPLE_RATES:
        raise OriginalAudioError("sound sample rate is not a supported PCM clock")
    _number(doc["frequency_hz"], "sound fundamental frequency", 30, 4000)
    duration = _number(doc["duration_ms"], "sound duration", 20, 3000)
    attack = _number(doc["attack_ms"], "sound attack", 0, 3000)
    release = _number(doc["release_ms"], "sound release", 0, 3000)
    if attack + release > duration:
        raise OriginalAudioError("audio attack/release envelope exceeds sound duration")
    _number(doc["gain_per_mille"], "limited sample amplitude", 0, 350)
    _number(doc["seed"], "deterministic original noise seed", 0, 2147483647)
    if rate * duration // 1000 > MAX_SAMPLES:
        raise OriginalAudioError("sound exceeds bounded PCM sample budget")
    return asset_id, doc


def _render_samples(doc: Mapping[str, Any]) -> bytes:
    """Integer-only oscillators and envelopes; byte-stable across platforms."""
    rate = doc["sample_rate_hz"]
    sample_count = rate * doc["duration_ms"] // 1000
    attack_count = rate * doc["attack_ms"] // 1000
    release_count = rate * doc["release_ms"] // 1000
    phase_delta = doc["frequency_hz"] * 65536
    gain = doc["gain_per_mille"]
    state = doc["seed"]
    out = bytearray(sample_count * 2)
    for i in range(sample_count):
        phase = (i * phase_delta // rate) & 65535
        if doc["waveform"] == "square":
            value = 32767 if phase < 32768 else -32768
        elif doc["waveform"] == "triangle":
            value = 32767 - (abs(phase - 32768) * 65535 // 32768)
        else:
            state = (1103515245 * state + 12345) & 0x7fffffff
            value = (state >> 15) - 32768
        attack_gain = (
            min(65536, i * 65536 // attack_count)
            if attack_count else 65536
        )
        release_gain = (
            min(65536, (sample_count - 1 - i) * 65536 // release_count)
            if release_count else 65536
        )
        envelope = min(attack_gain, release_gain)
        amplitude = value * gain * envelope // (1000 * 65536)
        struct.pack_into("<h", out, i * 2, max(-32768, min(32767, amplitude)))
    return bytes(out)


def _wav(pcm: bytes, rate: int) -> bytes:
    data_length = len(pcm)
    return (
        b"RIFF" + struct.pack("<I", 36 + data_length) + b"WAVE"
        + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
        + b"data" + struct.pack("<I", data_length) + pcm
    )


def compile_original_sound(record: Mapping[str, Any]) -> dict[str, Any]:
    asset_id, doc = _validated_source(record)
    pcm = _render_samples(doc)
    audio = _wav(pcm, doc["sample_rate_hz"])
    if len(audio) > MAX_WAV_BYTES:
        raise OriginalAudioError("sound output exceeds absolute audio file bound")
    evidence = {
        "schema_version": SCHEMA, "asset_id": asset_id,
        "source_record_id": record["record_id"],
        "source_revision": record["revision"],
        "source_sha256": record["source_sha256"],
        "sample_rate_hz": doc["sample_rate_hz"],
        "channels": 1, "bits_per_sample": 16,
        "duration_ms": doc["duration_ms"],
        "sample_count": len(pcm) // 2,
        "waveform": doc["waveform"],
        "peak_gain_per_mille": doc["gain_per_mille"],
        "pcm_sha256": sha256(pcm).hexdigest(),
        "wav_sha256": sha256(audio).hexdigest(),
        "original_procedural_source_only": True,
        "audio_playback_in_game_verified": False,
        "copyright_clearance_certified": False,
    }
    evidence["receipt_sha256"] = digest(evidence)
    verify_original_sound(record, audio, evidence)
    return {"wav": audio, "metadata": evidence}


def verify_original_sound(
    record: Mapping[str, Any], wav: bytes, metadata: Mapping[str, Any],
) -> dict[str, Any]:
    asset_id, doc = _validated_source(record)
    if not isinstance(wav, bytes) or len(wav) > MAX_WAV_BYTES or len(wav) < 46:
        raise OriginalAudioError("original sound archive lacks bounded WAV bytes")
    if not isinstance(metadata, Mapping):
        raise OriginalAudioError("original audio receipt missing")
    claimed = dict(metadata)
    receipt_sha = claimed.pop("receipt_sha256", None)
    if receipt_sha != digest(claimed):
        raise OriginalAudioError("original sound evidence receipt was modified")
    if (wav[0:4] != b"RIFF" or wav[8:12] != b"WAVE"
            or wav[12:16] != b"fmt " or wav[36:40] != b"data"
            or struct.unpack_from("<I", wav, 4)[0] != len(wav) - 8
            or struct.unpack_from("<I", wav, 40)[0] != len(wav) - 44
            or wav[16:36] != struct.pack(
                "<IHHIIHH", 16, 1, 1, doc["sample_rate_hz"],
                doc["sample_rate_hz"] * 2, 2, 16,
            )):
        raise OriginalAudioError("published WAV format or header is incompatible")
    pcm = wav[44:]
    if pcm != _render_samples(doc):
        raise OriginalAudioError("actual audio samples differ from original source waveform")
    if (metadata.get("schema_version") != SCHEMA
            or metadata.get("channels") != 1
            or metadata.get("bits_per_sample") != 16
            or metadata.get("sample_rate_hz") != doc["sample_rate_hz"]
            or metadata.get("duration_ms") != doc["duration_ms"]
            or metadata.get("waveform") != doc["waveform"]
            or metadata.get("peak_gain_per_mille") != doc["gain_per_mille"]
            or metadata.get("original_procedural_source_only") is not True
            or metadata.get("audio_playback_in_game_verified") is not False
            or metadata.get("copyright_clearance_certified") is not False
            or metadata.get("wav_sha256") != sha256(wav).hexdigest()
            or metadata.get("pcm_sha256") != sha256(pcm).hexdigest()
            or metadata.get("source_sha256") != record["source_sha256"]
            or metadata.get("asset_id") != asset_id
            or metadata.get("sample_count") != len(pcm) // 2
            or metadata.get("source_record_id") != record["record_id"]
            or metadata.get("source_revision") != record["revision"]):
        raise OriginalAudioError("audio source lineage or published PCM hashes differ")
    return {
        "schema_version": "skeleton.jeeves.original_audio_replay.v1",
        "asset_id": asset_id,
        "source_sha256": record["source_sha256"],
        "wav_sha256": sha256(wav).hexdigest(),
        "reconstructed_all_pcm_samples": True,
        "engine_playback_observed": False,
    }


def compile_original_sound_collection(
    records: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    candidates = [
        record for _, record in sorted(records.items())
        if isinstance(record.get("document"), dict)
        and record["document"].get("kind") == "procedural_pcm_sound"
    ]
    if len(candidates) > MAX_ASSETS:
        raise OriginalAudioError("original sound collection exceeds output budget")
    assets = [compile_original_sound(record) for record in candidates]
    names = [asset["metadata"]["asset_id"] for asset in assets]
    if len(names) != len(set(names)):
        raise OriginalAudioError("duplicate original sound resource identity")
    return {
        "schema_version": SCHEMA,
        "assets": assets,
        "count": len(assets),
        "wav_sha256_by_asset": {
            asset["metadata"]["asset_id"]: asset["metadata"]["wav_sha256"]
            for asset in assets
        },
    }


__all__ = [
    "OriginalAudioError", "compile_original_sound",
    "verify_original_sound", "compile_original_sound_collection",
]
