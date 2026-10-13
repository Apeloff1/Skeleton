"""Independent original offline oscillator and approved Studio playback regression."""
from __future__ import annotations
from copy import deepcopy
from contextlib import redirect_stdout,redirect_stderr
from hashlib import sha256
from io import BytesIO,StringIO
from pathlib import Path
import json
import tempfile
import unittest
import wave

from skeleton.ai.game_builder.advanced_rhythm_audio import (
    SAMPLE_RATE,MAX_RENDER_MS,RhythmAudioError,
    render_original_beat_wav,original_audio_receipt,
)
from skeleton.ai.game_builder.advanced_rhythm_runtime import default_layout
from skeleton.ai.game_builder.system_editors import make_editor_document
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html,SCRIPT
from skeleton.ai.game_builder.system_editor_cli import main


class OriginalAuthoredSoundtrackTests(unittest.TestCase):
    @staticmethod
    def settings(**overrides):
        return make_editor_document("rhythm",{
            "beat_count":8,"bpm":120,**overrides
        })["settings"]

    def test_original_pcm_has_real_audio_frames_and_stable_source_digest(self):
        cfg=self.settings()
        layout=default_layout(cfg,7)
        a=render_original_beat_wav(layout,cfg,duration_ms=1200)
        b=render_original_beat_wav(layout,cfg,duration_ms=1200)
        self.assertEqual(a,b)
        self.assertTrue(a.startswith(b"RIFF"))
        self.assertIn(b"WAVE",a[:16])
        with wave.open(BytesIO(a),"rb") as stream:
            self.assertEqual(stream.getnchannels(),1)
            self.assertEqual(stream.getsampwidth(),2)
            self.assertEqual(stream.getframerate(),SAMPLE_RATE)
            self.assertEqual(stream.getnframes(),1200*SAMPLE_RATE//1000)
            self.assertNotEqual(stream.readframes(stream.getnframes()),
                                b"\0"*(1200*SAMPLE_RATE//1000*2))
        receipt=original_audio_receipt(layout,cfg,duration_ms=1200)
        self.assertEqual(receipt["sha256"],sha256(a).hexdigest())
        self.assertEqual(receipt["bytes"],len(a))
        self.assertFalse(receipt["native_playback_certified"])
        self.assertFalse(receipt["original_audio_asset_required"])
        self.assertIn("no_third_party_samples",receipt["renderer"])

    def test_original_instruments_are_distinct_and_silence_is_genuinely_silent(self):
        soundtracks={}
        for instrument in ("original_sine","original_triangle",
                           "original_pulse","silent"):
            cfg=self.settings(instrument=instrument)
            layout=default_layout(cfg,0)
            data=render_original_beat_wav(layout,cfg,duration_ms=250)
            soundtracks[instrument]=data
        self.assertEqual(len(set(soundtracks.values())),4)
        with wave.open(BytesIO(soundtracks["silent"]),"rb") as w:
            self.assertEqual(set(w.readframes(w.getnframes())),{0})
        off=self.settings(sound_enabled=False)
        silent=render_original_beat_wav(default_layout(off,0),off,duration_ms=250)
        self.assertEqual(silent,soundtracks["silent"])

    def test_original_section_rendering_changes_proof_not_authoring_source(self):
        cfg=self.settings(beat_count=20)
        layout=default_layout(cfg,3)
        before=deepcopy(layout)
        first=render_original_beat_wav(layout,cfg,from_ms=0,duration_ms=2000)
        later=render_original_beat_wav(layout,cfg,from_ms=5000,duration_ms=2000)
        self.assertNotEqual(first,later)
        self.assertEqual(before,layout)
        receipt=original_audio_receipt(layout,cfg,from_ms=5000,duration_ms=2000)
        self.assertEqual(receipt["sha256"],sha256(later).hexdigest())
        self.assertEqual(receipt["window_start_ms"],5000)
        self.assertEqual(receipt["window_duration_ms"],2000)

    def test_render_is_bounded_and_rejects_boolean_or_float_offsets(self):
        cfg=self.settings()
        layout=default_layout(cfg,2)
        for kwargs in (
            {"duration_ms":50-1},{"duration_ms":MAX_RENDER_MS+1},
            {"from_ms":-1},{"from_ms":True},{"duration_ms":True},
            {"from_ms":600001},{"duration_ms":500.5},
        ):
            with self.subTest(value=kwargs):
                with self.assertRaises(RhythmAudioError):
                    render_original_beat_wav(layout,cfg,**kwargs)
        altered=deepcopy(layout)
        altered["notes"][0]["lane"]=200
        with self.assertRaises(ValueError):
            render_original_beat_wav(altered,cfg)

    def test_cli_never_overwrites_existing_original_soundtrack_and_requires_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            settings={"beat_count":4}
            source=make_advanced_scene("rhythm",settings,seed=9)
            src=root/"scene.json";prefs=root/"settings.json"
            output=root/"original.wav"
            src.write_text(json.dumps(source),encoding="utf-8")
            prefs.write_text(json.dumps(settings),encoding="utf-8")
            args=["rhythm-audio","--scene",str(src),"--settings",str(prefs),
                  "--seed","9","--duration-ms","400","--output",str(output)]
            with redirect_stdout(StringIO()),redirect_stderr(StringIO()):
                self.assertEqual(main(args),2)
            self.assertFalse(output.exists())
            stdout=StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(main(args+["--trusted-local-operator"]),0)
            proof=json.loads(stdout.getvalue())
            self.assertTrue(output.exists())
            self.assertEqual(proof["sha256"],sha256(output.read_bytes()).hexdigest())
            self.assertFalse(proof["native_playback_certified"])
            original=output.read_bytes()
            with redirect_stdout(StringIO()),redirect_stderr(StringIO()):
                self.assertEqual(main(args+["--trusted-local-operator"]),2)
            self.assertEqual(original,output.read_bytes())
            bad_source=root/"forged.json"
            stolen=deepcopy(source)
            stolen["layout"]["notes"][0]["at"]=200
            bad_source.write_text(json.dumps(stolen),encoding="utf-8")
            with redirect_stdout(StringIO()),redirect_stderr(StringIO()):
                self.assertEqual(main([
                    "rhythm-audio","--scene",str(bad_source),
                    "--settings",str(prefs),"--seed","9",
                    "--output",str(root/"forged.wav"),
                    "--trusted-local-operator"
                ]),2)
            self.assertFalse((root/"forged.wav").exists())

    def test_live_studio_playback_has_bounded_validated_original_preview(self):
        html=render_workspace_html("A"*32).decode("utf-8")
        for token in ("/api/rhythm-audio",
                      "rhythm-original-wav-preview",
                      "Synthesize reviewed original song audio",
                      "original oscillator","audio_base64",
                      "data:audio/wav;base64,",
                      "paintRhythmBeat","rhythm-play-lane",
                      "Run verified song clock","rhythm-play-kind",
                      "Original rhythm source edited"):
            self.assertIn(token.lower(),html.lower())
        self.assertIn("selectedRhythmNote",SCRIPT)
        self.assertIn("chord",SCRIPT)


if __name__=="__main__":
    unittest.main()
