"""Original audio: fixed-point reproducibility, bounds, provenance and CLI."""
from __future__ import annotations

import copy
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import wave

from skeleton.audio.pipeline import AudioError, AudioLimits
from skeleton.audio.original_synthesis import SoundPatch, synthesize

PATCH = Path(__file__).resolve().parents[1] / "audio/fixtures/harbor_chime.json"


class OriginalSynthesisTests(unittest.TestCase):
    def setUp(self):
        self.raw = json.loads(PATCH.read_text(encoding="utf-8"))
        self.patch = SoundPatch.from_mapping(self.raw)

    def test_deterministic_pcm_and_canonical_asset(self):
        first = synthesize(self.patch)
        second = synthesize(self.patch)
        self.assertEqual(first.wav_bytes, second.wav_bytes)
        self.assertEqual(first.wav_digest, second.wav_digest)
        self.assertEqual(first.asset.source_digest, self.patch.source_digest)
        self.assertEqual(first.asset.channels, 1)
        self.assertEqual(first.receipt()["license"], "CC0-1.0")
        self.assertTrue(AudioLimits(30000, 1, 48000, 3000000).admit(first.asset))
        with wave.open(BytesIO(first.wav_bytes), "rb") as reader:
            self.assertEqual(reader.getnchannels(), 1)
            self.assertEqual(reader.getsampwidth(), 2)
            self.assertEqual(reader.getframerate(), self.patch.sample_rate)
            self.assertEqual(reader.getnframes(), self.patch.sample_rate * self.patch.duration_ms // 1000)
            self.assertEqual(len(reader.readframes(reader.getnframes())),
                             2 * reader.getnframes())

    def test_all_waveforms_are_real_distinct_audio(self):
        digests = set()
        for waveform in ("square", "triangle", "saw", "noise"):
            raw = dict(self.raw, waveform=waveform)
            rendered = synthesize(SoundPatch.from_mapping(raw))
            self.assertNotEqual(rendered.wav_bytes[44:], bytes(len(rendered.wav_bytes) - 44))
            digests.add(rendered.wav_digest)
        self.assertEqual(len(digests), 4)

    def test_reject_untrusted_budget_and_provenance(self):
        cases = [
            ("version", True), ("version", 2), ("license", "unknown"),
            ("waveform", "speech"), ("sample_rate", 96000),
            ("sample_rate", 44101), ("frequency_millihz", 25000000),
            ("duration_ms", 30001), ("gain_permille", -1),
            ("attack_ms", 30001), ("release_ms", -1), ("seed", 0),
            ("seed", True), ("patch_id", "bad"), ("author", ""),
        ]
        for field, value in cases:
            raw = copy.deepcopy(self.raw)
            raw[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(AudioError):
                SoundPatch.from_mapping(raw)
        raw = dict(self.raw, extra="unreviewed")
        with self.assertRaises(AudioError):
            SoundPatch.from_mapping(raw)

    def test_attack_release_and_noise_seed_are_deterministic(self):
        first = synthesize(self.patch)
        changed = SoundPatch.from_mapping(dict(self.raw, seed=self.patch.seed + 1))
        # Seed only affects the noise waveform; the fixed-point tonal wave is unchanged.
        self.assertEqual(first.wav_digest, synthesize(changed).wav_digest)
        noise = dict(self.raw, waveform="noise")
        a = synthesize(SoundPatch.from_mapping(noise))
        b = synthesize(SoundPatch.from_mapping(dict(noise, seed=noise["seed"] + 1)))
        self.assertNotEqual(a.wav_digest, b.wav_digest)
        self.assertEqual(a.wav_bytes[44:46], b"\\x00\\x00")

    def test_cli_no_clobber_and_inspection(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "effect.wav"
            command = [sys.executable, "-m", "scripts.game.synthesize_original_sound",
                       str(PATCH), "--out", str(target)]
            first = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(first.returncode, 0, first.stderr)
            receipt = json.loads(first.stdout)
            self.assertEqual(receipt["wav_sha256"], synthesize(self.patch).wav_digest)
            self.assertEqual(target.read_bytes(), synthesize(self.patch).wav_bytes)
            second = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(second.returncode, 2)
            self.assertEqual(target.read_bytes(), synthesize(self.patch).wav_bytes)
            inspect = subprocess.run([sys.executable, "-m", "scripts.game.synthesize_original_sound",
                                      str(PATCH), "--inspect"],
                                     capture_output=True, text=True, check=False)
            self.assertEqual(inspect.returncode, 0, inspect.stderr)
            self.assertFalse(json.loads(inspect.stdout)["written"])


if __name__ == "__main__":
    unittest.main()
