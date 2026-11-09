"""Original media generation proof of byte outputs from synthetic evidence fixtures.

No proprietary ROM/music/image or native emulator is used.
"""
from __future__ import annotations

import hashlib
import io
import json
import unittest
import wave
import xml.etree.ElementTree as ET

from skeleton.jeeves.game_comparison_schema import digest
from skeleton.jeeves.game_comparison_inspiration import (
    InspirationError,build_original_inspiration_pack,
)


def fixture():
    games={}
    for gameid in ("alpha","beta"):
        games[gameid]={
            "id":gameid,"status":"actual_native_observations_captured",
            "source_sha256":digest({"fixture_only":gameid}),
            "core_sha256":digest({"fixture_core":gameid}),
            "phases":{
                stage:{"source":"actual_isolated_libretro",
                       "evidence_sha256":digest([gameid,stage])}
                for stage in ("earlier","middle","after")
            },
        }
    source={
        "schema_version":"skeleton.game.comparative_study_result.v1",
        "study_id":"synthetic_fixture_only",
        "games":games,
        "observer_notes":[],
    }
    source["result_sha256"]=digest(source)
    return source


class OriginalInspirationByteContracts(unittest.TestCase):
    def test_real_svg_wave_cutscene_mechanics_files(self):
        files,receipt=build_original_inspiration_pack(
            fixture(),game_ids=["alpha","beta"],genre="adventure",
            creative_brief="An original wandering sky-garden",author_seed=123,
        )
        self.assertEqual(len(files),12)
        self.assertEqual(receipt["generated_file_count"],12)
        self.assertFalse(receipt["source_game_rom_pixels_music_character_story_or_maps_copied"])
        self.assertFalse(receipt["large_language_model_training_performed"])
        for stage in ("earlier","middle","after"):
            vector=files[f"assets/{stage}_original.svg"]
            root=ET.fromstring(vector)
            self.assertTrue(root.tag.endswith("svg"))
            with wave.open(io.BytesIO(files[f"music/{stage}_original.wav"]),"rb") as audio:
                self.assertEqual(audio.getnchannels(),1)
                self.assertEqual(audio.getframerate(),16000)
                self.assertGreater(audio.getnframes(),0)
            shots=json.loads(files[f"cutscenes/{stage}_original.json"])
            mechanics=json.loads(files[f"mechanics/{stage}_original.json"])
            self.assertFalse(shots["actual_video_rendered"])
            self.assertFalse(mechanics["production_gameplay_implemented"])
            for item in receipt["stages"][("earlier","middle","after").index(stage)]["generated_file_receipts"]:
                self.assertEqual(hashlib.sha256(files[item["path"]]).hexdigest(),item["sha256"])

    def test_tampered_evidence_fails_closed(self):
        source=fixture()
        source["games"]["alpha"]["source_sha256"]="0"*64
        with self.assertRaises(InspirationError):
            build_original_inspiration_pack(
                source,game_ids=["alpha","beta"],genre="puzzle",creative_brief="Invented map",
            )

    def test_invalid_selection_and_brief_rejected(self):
        with self.assertRaises(InspirationError):
            build_original_inspiration_pack(
                fixture(),game_ids=["alpha","alpha"],genre="racing",creative_brief="Fresh route",
            )
        with self.assertRaises(InspirationError):
            build_original_inspiration_pack(
                fixture(),game_ids=["alpha","beta"],genre="other",creative_brief="Fresh route",
            )


if __name__=="__main__":
    unittest.main()
