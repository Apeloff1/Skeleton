"""Original deterministic audio synthesis and source-authorship regressions."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest

from skeleton.forge.creator.command_surface import build_creator_command
from skeleton.jeeves.ai.studio_creator_source import CreatorProjectSourceStore
from skeleton.jeeves.ai.studio_interaction_contract import digest
from skeleton.jeeves.ai.studio_original_audio import (
    OriginalAudioError, compile_original_sound,
    compile_original_sound_collection, verify_original_sound,
)


def original_sound() -> dict:
    return {
        "kind": "procedural_pcm_sound",
        "asset_id": "original-footstep",
        "waveform": "triangle", "frequency_hz": 220,
        "duration_ms": 240, "attack_ms": 10, "release_ms": 40,
        "gain_per_mille": 250, "seed": 42, "sample_rate_hz": 16000,
    }


def sound_record() -> dict:
    doc = original_sound()
    return {
        "record_id": "footstep-source", "facet": "audio_forge",
        "revision": 1, "depends_on": [], "document": doc,
        "source_sha256": digest([
            "footstep-source", "audio_forge", 1, doc, [],
        ]),
    }


def reseal(record: dict) -> dict:
    record["source_sha256"] = digest([
        record["record_id"], record["facet"], record["revision"],
        record["document"], record["depends_on"],
    ])
    return record


class OriginalAudioForgeTests(unittest.TestCase):
    def test_original_source_produces_actual_playable_wav_bytes(self):
        source = sound_record()
        emitted = compile_original_sound(source)
        body, meta = emitted["wav"], emitted["metadata"]
        self.assertEqual(body[:4], b"RIFF")
        self.assertEqual(body[8:12], b"WAVE")
        self.assertEqual(body[12:16], b"fmt ")
        self.assertEqual(body[36:40], b"data")
        self.assertEqual(struct.unpack_from("<H", body, 22)[0], 1)
        self.assertEqual(struct.unpack_from("<I", body, 24)[0], 16000)
        self.assertEqual(struct.unpack_from("<H", body, 34)[0], 16)
        self.assertEqual(meta["sample_count"], 3840)
        self.assertEqual(meta["wav_sha256"], sha256(body).hexdigest())
        self.assertTrue(
            verify_original_sound(
                source, body, meta,
            )["reconstructed_all_pcm_samples"]
        )
        self.assertFalse(meta["audio_playback_in_game_verified"])

    def test_source_produces_identical_audio_on_repeated_compilation(self):
        self.assertEqual(
            compile_original_sound(sound_record()),
            compile_original_sound(sound_record()),
        )

    def test_all_reviewed_oscillators_are_independent_reproducible_pcm(self):
        hashes = set()
        for waveform in ("triangle", "square", "noise"):
            source = sound_record()
            source["document"]["waveform"] = waveform
            generated = compile_original_sound(reseal(source))
            hashes.add(generated["metadata"]["pcm_sha256"])
            self.assertTrue(verify_original_sound(
                source, generated["wav"], generated["metadata"],
            )["reconstructed_all_pcm_samples"])
        self.assertEqual(len(hashes), 3)

    def test_authored_attack_and_release_silence_ends(self):
        output = compile_original_sound(sound_record())
        pcm = output["wav"][44:]
        first, last = struct.unpack_from("<h", pcm, 0)[0], struct.unpack_from(
            "<h", pcm, len(pcm) - 2,
        )[0]
        self.assertEqual(first, 0)
        self.assertEqual(last, 0)

    def test_amplitude_is_bounded_even_at_loudest_allowed_setting(self):
        source = sound_record()
        source["document"]["gain_per_mille"] = 350
        source["document"]["waveform"] = "square"
        raw = compile_original_sound(reseal(source))["wav"][44:]
        samples = struct.unpack("<" + "h" * (len(raw) // 2), raw)
        self.assertLessEqual(max(abs(value) for value in samples), 11470)

    def test_reject_forged_revision_before_waveform_synthesis(self):
        source = sound_record()
        source["document"]["frequency_hz"] = 400
        with self.assertRaisesRegex(OriginalAudioError, "persisted original revision"):
            compile_original_sound(source)

    def test_reject_unknown_waveform_without_execution(self):
        source = sound_record()
        source["document"]["waveform"] = "plugin:external-synth"
        with self.assertRaisesRegex(OriginalAudioError, "reviewed oscillator"):
            compile_original_sound(reseal(source))

    def test_reject_excessive_gain_and_duration(self):
        for key, value in (
            ("gain_per_mille", 500),
            ("duration_ms", 5000),
            ("sample_rate_hz", 192000),
        ):
            with self.subTest(parameter=key):
                source = sound_record()
                source["document"][key] = value
                with self.assertRaises(OriginalAudioError):
                    compile_original_sound(reseal(source))

    def test_reject_impossible_envelope(self):
        source = sound_record()
        source["document"]["attack_ms"] = 230
        source["document"]["release_ms"] = 100
        with self.assertRaisesRegex(OriginalAudioError, "envelope"):
            compile_original_sound(reseal(source))

    def test_reject_waveform_sample_tampering_with_full_metadata_reseal(self):
        source = sound_record()
        out = compile_original_sound(source)
        forged = bytearray(out["wav"])
        forged[44] ^= 4
        evidence = deepcopy(out["metadata"])
        evidence["pcm_sha256"] = sha256(bytes(forged)[44:]).hexdigest()
        evidence["wav_sha256"] = sha256(bytes(forged)).hexdigest()
        evidence["receipt_sha256"] = digest({
            key: value for key, value in evidence.items()
            if key != "receipt_sha256"
        })
        with self.assertRaisesRegex(OriginalAudioError, "actual audio samples"):
            verify_original_sound(source, bytes(forged), evidence)

    def test_reject_corrupt_wav_header(self):
        source = sound_record()
        out = compile_original_sound(source)
        forged = bytearray(out["wav"])
        forged[20:22] = b"\x03\x00"
        with self.assertRaisesRegex(OriginalAudioError, "WAV format"):
            verify_original_sound(source, bytes(forged), out["metadata"])

    def test_reject_wrong_creator_facet(self):
        source = sound_record()
        source["facet"] = "sprite_forge"
        with self.assertRaisesRegex(OriginalAudioError, "audio_forge"):
            compile_original_sound(source)

    def test_duplicate_resource_names_refuse_collection(self):
        first = sound_record()
        second = deepcopy(first)
        second["record_id"] = "second-source"
        reseal(second)
        with self.assertRaisesRegex(OriginalAudioError, "duplicate"):
            compile_original_sound_collection({
                "footstep-source": first, "second-source": second,
            })

    def test_invalid_audio_fails_before_creating_durable_game_source(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            export = root / "export"
            export.mkdir()
            with CreatorProjectSourceStore(
                root / "original-source.sqlite",
                project_id="audio-game", export_root=export,
            ) as owner:
                bad = original_sound()
                bad["gain_per_mille"] = 800
                with self.assertRaises(OriginalAudioError):
                    owner.create(build_creator_command(
                        "create", project_id="audio-game",
                        payload={"intent": {
                            "record_id": "footstep-source", "facet": "audio_forge",
                            "document": bad, "depends_on": [],
                        }},
                    ))
                self.assertEqual(owner.snapshot()["source_count"], 0)

    def test_valid_audio_survives_creator_source_restart(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            export = root / "export"
            export.mkdir()
            store = CreatorProjectSourceStore(
                root / "original-source.sqlite",
                project_id="audio-game", export_root=export,
            )
            self.addCleanup(store.close)
            result = store.create(build_creator_command(
                "create", project_id="audio-game",
                payload={"intent": {
                    "record_id": "footstep-source", "facet": "audio_forge",
                    "document": original_sound(), "depends_on": [],
                }},
            ))
            self.assertEqual(result["revision"], 1)
            self.assertTrue(result["source_written_to_sqlite"])
            store.close()
            reopened = CreatorProjectSourceStore(
                root / "original-source.sqlite",
                project_id="audio-game", export_root=export,
            )
            try:
                exported = compile_original_sound_collection(reopened._records)
                self.assertEqual(exported["count"], 1)
                self.assertEqual(exported["assets"][0]["metadata"]["asset_id"],
                                 "original-footstep")
            finally:
                reopened.close()


if __name__ == "__main__":
    unittest.main()
