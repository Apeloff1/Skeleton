"""Original 256-beat performance: no snapshot trust or shared cap bypass."""
from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import json
import tempfile
import unittest

from skeleton.ai.game_builder.advanced_rhythm_longrun import (
    SCHEMA,MAX_ACTIONS,RhythmLongChartError,
    run_long_rhythm,verify_long_rhythm,continue_long_rhythm,
)
from skeleton.ai.game_builder.advanced_rhythm_runtime import default_layout
from skeleton.ai.game_builder.system_editors import make_editor_document
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    AdvancedRuntimeError,run_advanced_session,
)
from skeleton.ai.game_builder.system_editor_cli import main
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html


def genuine_autoplay_script(config,seed=0):
    """Build a transparent simulation rehearsal from original authored events.

    This is a *test fixture itinerary* using publicly known note positions.
    It does not run behind a user-facing button or declare human skill.
    The longrun engine only accepts individual legal actions at times actually
    reached by server-controlled wait commands.
    """
    cfg=make_editor_document("rhythm",config)["settings"]
    chart=default_layout(cfg,seed)
    actions=[];clock=chart["offset_ms"];held=[]
    for n in chart["notes"]:
        deadline=n["at"]+chart["offset_ms"]
        while clock<deadline:
            if deadline-clock>=500:
                actions.append("wait:500");clock+=500
            else:
                remaining=deadline-clock
                for step in (250,125,100,50,25,20,10):
                    if remaining>=step:
                        actions.append("wait:"+str(step))
                        clock+=step;break
                else:
                    raise ValueError("authored beat time needs finer original clock resolution")
        for h in list(held):
            if h["end"]==clock:
                actions.append("release:"+str(h["lane"]))
                held.remove(h)
        lane=n["lane"];kind=n["kind"]
        if kind=="mine":continue
        if kind=="tap":
            actions.append("tap:"+str(lane))
        elif kind=="slide":
            actions.append("flick:"+str(lane))
        elif kind=="chord":
            actions.append("chord:"+str(lane)+":"+str(n["partner"]))
        elif kind=="hold":
            actions.append("press:"+str(lane))
            held.append({"lane":lane,"end":clock+n["duration"]})
    for h in held:
        if h["end"]-clock!=500:
            raise ValueError("test rehearsal hold cannot settle on authored 500ms beat")
        actions.append("wait:500");clock+=500
        actions.append("release:"+str(h["lane"]))
    if chart["notes"][-1]["kind"]=="mine":
        actions.append("wait:500")
    actions.append("finish")
    return actions


class OriginalFullLengthRhythmTests(unittest.TestCase):
    @staticmethod
    def settings(count=256):
        return {"beat_count":count,"bpm":120,"starting_health":1000,
                "miss_health":2,"fail_mode":"finish_only"}

    def test_256_genuinely_scored_beats_pass_longrun_while_128_action_gate_remains(self):
        cfg=self.settings()
        actions=genuine_autoplay_script(cfg,seed=0)
        self.assertGreater(len(actions),128)
        self.assertLessEqual(len(actions),MAX_ACTIONS)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("rhythm",cfg,actions)
        record=run_long_rhythm(cfg,actions,seed=0,checkpoint_interval=64)
        self.assertEqual(record["schema"],SCHEMA)
        self.assertEqual(record["turn_count"],len(actions))
        self.assertGreaterEqual(record["checkpoint_count"],5)
        self.assertTrue(record["finished"])
        self.assertTrue(record["victory"])
        self.assertEqual(record["state"]["accuracy"],10000)
        self.assertEqual(record["state"]["miss"],0)
        self.assertEqual(record["state"]["stray"],0)
        self.assertEqual(record["state"]["chart"]["beats"],256)
        self.assertTrue(verify_long_rhythm(record,cfg))
        self.assertEqual(record["head_digest"],record["checkpoints"][-1]["digest"])
        self.assertFalse(record["native_execution_certified"])
        self.assertFalse(record["audio_certified"])
        self.assertFalse(record["untrusted_state_promoted"])
        for i in range(1,record["checkpoint_count"]):
            self.assertEqual(record["checkpoints"][i]["previous_digest"],
                             record["checkpoints"][i-1]["digest"])

    def test_partial_original_performance_resumes_from_independently_replayed_history(self):
        cfg=self.settings(32);actions=genuine_autoplay_script(cfg,seed=0)
        split=len(actions)//2
        first=run_long_rhythm(cfg,actions[:split],checkpoint_interval=16)
        self.assertTrue(verify_long_rhythm(first,cfg))
        self.assertFalse(first["finished"])
        resumed=continue_long_rhythm(first,actions[split:],cfg)
        direct=run_long_rhythm(cfg,actions,checkpoint_interval=16)
        self.assertEqual(resumed,direct)
        self.assertTrue(resumed["victory"])
        with self.assertRaises(RhythmLongChartError):
            continue_long_rhythm(resumed,["tap:0"],cfg)

    def test_signed_chart_stays_original_and_binds_full_checkpoint_history(self):
        cfg=self.settings(32)
        source=make_advanced_scene("rhythm",cfg,seed=4)
        actions=genuine_autoplay_script(cfg,seed=4)
        record=run_long_rhythm(cfg,actions,seed=4,scene=source,
                               checkpoint_interval=16)
        self.assertTrue(verify_long_rhythm(record,cfg))
        self.assertEqual(record["scene_digest"],source["digest"])
        for mutate in (
            lambda r:r["state"].update(score=99999999),
            lambda r:r["state"].update(accuracy=0),
            lambda r:r["checkpoints"][0].update(previous_digest="0"*64),
            lambda r:r["checkpoints"][-1].update(state_digest="0"*64),
            lambda r:r.update(head_digest="a"*64),
            lambda r:r.update(native_execution_certified=True),
            lambda r:r["source"]["layout"]["notes"][0].update(lane=100),
            lambda r:r.update(checkpoint_interval=14),
            lambda r:r["actions"].append("force_victory"),
        ):
            altered=deepcopy(record);mutate(altered)
            with self.assertRaises((ValueError,TypeError,KeyError)):
                verify_long_rhythm(altered,cfg)
        with self.assertRaises((ValueError,TypeError,KeyError)):
            verify_long_rhythm(record,{**cfg,"bpm":121})
        with self.assertRaises(RhythmLongChartError):
            continue_long_rhythm(record,["tap:0"],cfg)

    def test_malicious_oversized_or_noncanonical_budgets_fail_closed(self):
        cfg=self.settings(16)
        for invalid in (True,0,15,129,4096):
            with self.assertRaises(RhythmLongChartError):
                run_long_rhythm(cfg,[],checkpoint_interval=invalid)
        for inputs in (["force_win"],["wait:1"],["inspect"]*(MAX_ACTIONS+1),
                       None,"[]"):
            with self.assertRaises(RhythmLongChartError):
                run_long_rhythm(cfg,inputs)
        with self.assertRaises(RhythmLongChartError):
            run_long_rhythm(cfg,[],seed=True)
        with self.assertRaises(RhythmLongChartError):
            verify_long_rhythm({"schema":SCHEMA})
        blank=run_long_rhythm(cfg,[])
        self.assertTrue(verify_long_rhythm(blank,cfg))
        self.assertEqual(blank["head_digest"],blank["genesis_digest"])

    def test_cli_full_source_verified_song_export_and_replay_uses_original_charts(self):
        cfg=self.settings(8)
        actions=genuine_autoplay_script(cfg)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);setting=root/"config.json";inputs=root/"actions.json"
            receipt=root/"receipt.json"
            setting.write_text(json.dumps(cfg),encoding="utf-8")
            inputs.write_text(json.dumps(actions),encoding="utf-8")
            output=StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["rhythm-longrun","--settings",str(setting),
                     "--actions",str(inputs),"--checkpoint-interval","16"]),0)
            source=json.loads(output.getvalue())
            self.assertTrue(source["victory"])
            receipt.write_text(json.dumps(source),encoding="utf-8")
            output=StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["rhythm-longrun-verify","--settings",
                  str(setting),"--record",str(receipt)]),0)
            self.assertTrue(json.loads(output.getvalue())["verified"])

    def test_studio_long_chart_uses_existing_source_and_no_auto_approval(self):
        page=render_workspace_html("A"*32).decode("utf-8")
        for marker in ("/api/rhythm-longrun","rhythm-longrun-actions",
                       "rhythm-longrun-proof","originalRhythmLongrunRecord",
                       "independently_verified","native_hardware_certified"):
            self.assertIn(marker,page)


if __name__=="__main__":
    unittest.main()
