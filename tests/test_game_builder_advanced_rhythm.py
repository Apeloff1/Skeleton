"""Adversarial original rhythm game, replay, timing, and source custody."""
from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
import unittest

from skeleton.ai.game_builder.advanced_rhythm_runtime import (
    ACTIONS,LANES,KINDS,RhythmActionError,default_layout,
    normalize_layout,start,step,
)
from skeleton.ai.game_builder.system_editors import (
    catalog,make_editor_document,SystemEditorError,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    ENGINES,ACTION_HELP,AdvancedRuntimeError,
    run_advanced_session,verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    SceneError,make_advanced_scene,validate_advanced_scene,
)
from skeleton.ai.game_builder.advanced_gameplay_save import (
    export_advanced_savegame,import_advanced_savegame,continue_advanced_savegame,
)
from skeleton.ai.game_builder.system_editor_assembly import compile_system_assembly


class OriginalTimingStudioTests(unittest.TestCase):
    @staticmethod
    def easy(**kwargs):
        return {"beat_count":4,"bpm":120,"hold_notes":False,"chords":False,
                "slides":False,"mines":False,**kwargs}

    def test_eighteenth_editor_controls_and_original_registered_actions(self):
        self.assertIn("rhythm",ENGINES)
        self.assertEqual(set(ACTIONS),set(ACTION_HELP["rhythm"]))
        spec=next(x for x in catalog() if x["id"]=="rhythm")
        self.assertEqual(spec["runtime_maturity"],"advanced_reference_runtime")
        self.assertEqual(spec["progression_floor"],"advanced")
        self.assertEqual(len(spec["fields"]),42)
        self.assertEqual(len(set(ACTIONS)),len(ACTIONS))
        self.assertGreaterEqual(len(ACTIONS),45)

    def test_original_seeded_charts_have_exact_typed_tempos_and_note_custody(self):
        for seed in (0,1,5,17,100):
            cfg=make_editor_document("rhythm")["settings"]
            authored=default_layout(cfg,seed)
            self.assertEqual(len(authored["notes"]),16)
            self.assertEqual(authored,normalize_layout(cfg,authored))
            self.assertEqual(authored["style"],"original_synth")
            self.assertEqual(authored["notes"][0]["at"],0)
            scene=make_advanced_scene("rhythm",seed=seed)
            self.assertEqual(validate_advanced_scene(scene),scene)
            session=run_advanced_session("rhythm",seed=seed,scene=scene)
            self.assertTrue(verify_advanced_session(session))
            self.assertEqual(session["state"]["clock_ms"],0)
            self.assertEqual(session["state"]["score"],0)
            self.assertFalse(session["native_hardware_verified"])

    def test_four_real_perfect_hits_with_clock_beat_judgement_clear_chart(self):
        rules=self.easy()
        cfg=make_editor_document("rhythm",rules)["settings"]
        notes=default_layout(cfg,0)["notes"]
        actions=[]
        now=0
        for n in notes:
            delta=n["at"]-now
            while delta>=500:
                actions.append("wait:500");delta-=500;now+=500
            if delta:
                actions.append("wait:"+str(delta));now+=delta
            actions.append("tap:"+str(n["lane"]))
        actions.extend(["wait:500","finish"])
        session=run_advanced_session("rhythm",rules,actions)
        self.assertTrue(verify_advanced_session(session,rules))
        s=session["state"]
        self.assertEqual(s["perfect"],4)
        self.assertEqual(s["miss"],0)
        self.assertEqual(s["hit_count"],4)
        self.assertEqual(s["accuracy"],10000)
        self.assertEqual(s["rank"],"SS")
        self.assertTrue(session["terminal"])
        self.assertTrue(s["victory"])
        self.assertGreaterEqual(s["score"],4*cfg["perfect_points"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("rhythm",rules,actions+["inspect"])

    def test_timestamp_forgery_or_mashing_does_not_mint_hit_score(self):
        rules=self.easy(beat_count=2)
        base=run_advanced_session("rhythm",rules,["tap:0"])
        self.assertEqual(base["state"]["perfect"],1)
        attempt=run_advanced_session("rhythm",rules,["tap:0","tap:0","tap:0"])
        self.assertEqual(attempt["state"]["perfect"],1)
        self.assertEqual(attempt["state"]["stray"],2)
        self.assertEqual(attempt["state"]["combo"],0)
        self.assertEqual(attempt["state"]["score"],base["state"]["score"])
        for illegal in ("tap:-1","tap:6","set_score:999","stamp:500",
                        "autoplay","wait:1","win","tap:0:500"):
            with self.assertRaises(AdvancedRuntimeError):
                run_advanced_session("rhythm",rules,[illegal])

    def test_real_one_time_mines_chords_slides_and_hold_releases(self):
        rules={"beat_count":30,"bpm":120,"starting_health":200}
        cfg=make_editor_document("rhythm",rules)["settings"]
        notes=default_layout(cfg,0)["notes"]
        self.assertTrue(any(n["kind"]=="slide" for n in notes))
        self.assertTrue(any(n["kind"]=="chord" for n in notes))
        self.assertTrue(any(n["kind"]=="hold" for n in notes))
        self.assertTrue(any(n["kind"]=="mine" for n in notes))
        state=start(cfg,0)
        for note in notes:
            wanted=note["at"]
            while state["clock_ms"]<wanted:
                step(state,cfg,"wait:500")
            lane=note["lane"]
            if note["kind"]=="tap":
                step(state,cfg,"tap:"+str(lane))
            elif note["kind"]=="chord":
                step(state,cfg,"chord:"+str(lane)+":"+str(note["partner"]))
            elif note["kind"]=="slide":
                step(state,cfg,"flick:"+str(lane))
            elif note["kind"]=="hold":
                step(state,cfg,"press:"+str(lane))
                self.assertIn(note["id"],state["held"])
                step(state,cfg,"wait:500")
                step(state,cfg,"release:"+str(lane))
                self.assertNotIn(note["id"],state["held"])
            else:
                step(state,cfg,"tap:"+str(lane))
                self.assertGreater(state["mines_hit"],0)
        self.assertGreater(state["perfect"],0)
        self.assertTrue(all(x is not None for x in state["judgements"]))
        self.assertEqual(state["mines_hit"],1)
        step(state,cfg,"finish")
        self.assertTrue(state["finished"])

    def test_unpressed_holds_cannot_claim_reward_and_missed_release_costs_health(self):
        cfg=make_editor_document("rhythm",{"beat_count":5})["settings"]
        notes=default_layout(cfg,0)["notes"]
        note=next(n for n in notes if n["kind"]=="hold")
        s=start(cfg,0)
        while s["clock_ms"]<note["at"]:
            step(s,cfg,"wait:500")
        with self.assertRaises(RhythmActionError):
            step(s,cfg,"release:"+str(note["lane"]))
        step(s,cfg,"press:"+str(note["lane"]))
        self.assertEqual(s["judgements"][note["id"]],None)
        step(s,cfg,"wait:1000")
        self.assertEqual(s["judgements"][note["id"]],"miss")
        self.assertEqual(s["pressed"],{})
        self.assertGreater(s["miss"],0)

    def test_trap_mine_avoided_only_after_actual_timing_window_expired(self):
        rules={"beat_count":30,"bpm":120,"starting_health":1000,"fail_mode":"finish_only"}
        cfg=make_editor_document("rhythm",rules)["settings"]
        mine=next(n for n in default_layout(cfg,0)["notes"] if n["kind"]=="mine")
        state=start(cfg,0)
        while state["clock_ms"]<=mine["at"]+cfg["hit_window_ms"]:
            step(state,cfg,"wait:500")
        self.assertEqual(state["judgements"][mine["id"]],"mine_avoided")
        self.assertEqual(state["mines_avoided"],1)
        self.assertEqual(state["mines_hit"],0)

    def test_finite_heart_health_and_misses_are_real_in_health_mode(self):
        rules=self.easy(starting_health=10,miss_health=10)
        session=run_advanced_session("rhythm",rules,["wait:500"])
        self.assertTrue(session["terminal"])
        self.assertTrue(session["state"]["failed"])
        self.assertEqual(session["state"]["health"],0)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("rhythm",rules,["wait:500","tap:1"])
        finish_only=run_advanced_session("rhythm",
                          {**rules,"fail_mode":"finish_only"},["wait:500"])
        self.assertFalse(finish_only["terminal"])
        self.assertEqual(finish_only["state"]["health"],0)

    def test_strict_signed_source_rejects_fake_notes_tempos_and_digests(self):
        rules=self.easy()
        config=make_editor_document("rhythm",rules)["settings"]
        scene=make_advanced_scene("rhythm",rules,seed=3)
        for mutation in (
            lambda x:x["notes"][0].update(id=2),
            lambda x:x["notes"][0].update(lane=99),
            lambda x:x["notes"][0].update(at=-1),
            lambda x:x["notes"][1].update(at=0),
            lambda x:x["notes"][1].update(kind="pirated_sample"),
            lambda x:x["notes"][1].update(duration=999),
            lambda x:x["notes"][1].update(partner=0),
            lambda x:x["notes"][1].update(script="exec"),
            lambda x:x.update(bpm=600),
            lambda x:x.update(style="recording_from_protected_game"),
            lambda x:x.update(title="../notoriginal"),
        ):
            altered=deepcopy(scene["layout"])
            mutation(altered)
            with self.subTest(mutation=str(mutation)):
                with self.assertRaises(RhythmActionError):
                    normalize_layout(config,altered)
        changed=deepcopy(scene)
        changed["layout"]["notes"][2]["lane"]=(changed["layout"]["notes"][2]["lane"]+1)%4
        with self.assertRaises(SceneError):
            validate_advanced_scene(changed,rules)
        rebuilt=make_advanced_scene("rhythm",rules,seed=3,layout=changed["layout"])
        self.assertNotEqual(rebuilt["digest"],scene["digest"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("rhythm",rules,seed=4,scene=scene)

    def test_portable_verified_saves_reject_fake_timing_or_score_receipts(self):
        rules=self.easy()
        scene=make_advanced_scene("rhythm",rules,seed=8)
        report=run_advanced_session("rhythm",rules,["tap:0"],seed=8,scene=scene)
        self.assertTrue(verify_advanced_session(report,rules))
        save=export_advanced_savegame(report,rules)
        self.assertEqual(import_advanced_savegame(save)["session"],report)
        resumed=continue_advanced_savegame(save,["wait:500"])
        self.assertTrue(import_advanced_savegame(resumed)["verified"])
        for mutate in (
            lambda s:s.update(clock_ms=30000),
            lambda s:s.update(score=999999),
            lambda s:s.update(victory=True),
            lambda s:s["judgements"].__setitem__(1,"perfect"),
            lambda s:s.update(combo=999),
        ):
            forged=deepcopy(report)
            mutate(forged["state"])
            with self.assertRaises(AdvancedRuntimeError):
                verify_advanced_session(forged,rules)

    def test_real_hybrid_original_chart_and_offline_cli(self):
        rules=self.easy()
        scene=make_advanced_scene("rhythm",rules,seed=2)
        assembly=compile_system_assembly("original_rhythm_reference",
               [make_editor_document("rhythm",rules)],authorized=True,scenes=[scene])
        self.assertEqual(assembly["authored_scene_count"],1)
        self.assertEqual(assembly["advanced_runtime_evidence"][0]["editor"],"rhythm")
        self.assertFalse(assembly["ready_for_release"])
        from skeleton.ai.game_builder.system_editor_cli import main
        output=io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["play","--editor","rhythm","--seed","2"]),0)
        report=json.loads(output.getvalue())
        self.assertTrue(verify_advanced_session(report))
        self.assertFalse(report["native_hardware_verified"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("rhythm",actions=["inspect"]*129)


if __name__=="__main__":
    unittest.main()
