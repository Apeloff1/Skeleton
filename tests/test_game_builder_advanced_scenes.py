"""End-to-end adversarial authored gameplay scenes and verified portable saves."""
from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import http.client
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest

from skeleton.ai.game_builder.advanced_level_scenes import (
    SceneError, make_advanced_scene, validate_advanced_scene, scene_path,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    AdvancedRuntimeError, run_advanced_session, verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_gameplay_save import (
    SavegameError, export_advanced_savegame, import_advanced_savegame,
    continue_advanced_savegame,
)
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace, WorkspaceError
from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from skeleton.ai.game_builder.system_editor_cli import main as editor_cli
from skeleton.ai.game_builder.system_editors import editor_source,make_editor_document


EMPTY_SHA="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class AuthoredSceneTests(unittest.TestCase):
    def test_all_five_families_generate_signed_replayable_scenes(self):
        for engine in ("platformer","tactics","tower_defense","racing","survival"):
            with self.subTest(engine=engine):
                scene=make_advanced_scene(engine,seed=2)
                self.assertEqual(scene,validate_advanced_scene(scene))
                self.assertEqual(scene,make_advanced_scene(engine,seed=2))
                self.assertEqual(scene_path(scene),"scenes/advanced_"+engine+"_scene_01.json")
                session=run_advanced_session(engine,actions=[],seed=2,scene=scene)
                self.assertTrue(verify_advanced_session(session))
                self.assertEqual(session["scene_digest"],scene["digest"])
                self.assertEqual(session["scene"],scene)
                self.assertFalse(session["publication_certified"])

    def test_authored_platformer_custom_layout_affects_gameplay(self):
        scene=make_advanced_scene("platformer",seed=3,layout={
            "spawn_x":2,"exit_x":25,"hazards":[9,15],
            "collectibles":[5,18],"checkpoints":[12,20]})
        session=run_advanced_session("platformer",actions=["right"],seed=3,scene=scene)
        self.assertEqual(session["state"]["exit_x"],25)
        self.assertEqual(session["state"]["spikes"],[9,15])
        self.assertEqual(session["state"]["x"],5)
        self.assertEqual(session["state"]["crystals"],[5])
        self.assertTrue(verify_advanced_session(session))
        altered=deepcopy(scene);altered["layout"]["hazards"]=[7,15]
        with self.assertRaises(SceneError):
            run_advanced_session("platformer",actions=[],seed=3,scene=altered)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("platformer",actions=[],seed=4,scene=scene)

    def test_authored_tactics_geometry_legal_and_isolation_rejected(self):
        layout=make_advanced_scene("tactics")["layout"]
        layout["obstacles"]=[[3,2],[3,3],[3,4]]
        layout["objective"]=[8,0]
        custom=make_advanced_scene("tactics",layout=layout)
        game=run_advanced_session("tactics",scene=custom,
                                   actions=["east","end_turn"])
        self.assertEqual(game["state"]["obstacles"],layout["obstacles"])
        self.assertTrue(verify_advanced_session(game))
        layout["obstacles"]=[[4,y] for y in range(10)]
        with self.assertRaises(SceneError):
            make_advanced_scene("tactics",layout=layout)

    def test_tower_slots_and_wave_count_are_actually_runtime_enforced(self):
        scene=make_advanced_scene("tower_defense",layout={
            "build_slots":[1],"waves":2})
        a=run_advanced_session("tower_defense",scene=scene,
                               actions=["build:1","tick:4"])
        self.assertEqual(a["state"]["allowed_slots"],[1])
        self.assertEqual(a["state"]["wave_limit"],2)
        self.assertTrue(verify_advanced_session(a))
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("tower_defense",scene=scene,actions=["build:0"])

    def test_custom_circuit_and_finite_survival_geography(self):
        track=make_advanced_scene("racing",seed=1,layout={
            "corners":[5,10,15],"track_obstacle":8,
            "weather":"storm","starting_lane":-1})
        race=run_advanced_session("racing",seed=1,scene=track,
                                  actions=["accelerate","steer_right"])
        self.assertEqual(race["state"]["weather"],"storm")
        self.assertEqual(race["state"]["corners"],[5,10,15])
        self.assertEqual(race["state"]["lane"],0)
        region=make_advanced_scene("survival")["layout"]
        region["regions"]=region["regions"][:2]
        region["regions"][1]["wood_stock"]=1
        region["starting_region"]=1
        custom=make_advanced_scene("survival",layout=region)
        game=run_advanced_session("survival",scene=custom,actions=["gather_wood"])
        self.assertEqual(game["state"]["region"],1)
        self.assertEqual(game["state"]["regions"][1]["wood_stock"],0)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("survival",scene=custom,
                                 actions=["gather_wood","gather_wood"])

    def test_fail_closed_geometry_and_configuration_binding(self):
        scene=make_advanced_scene("platformer")
        for replacement in [
            {"hazards":[5,5]},{"hazards":[-1]},{"checkpoints":[10,5]},
            {"spawn_x":10,"exit_x":9},{"hazards":[20],"checkpoints":[20]},
            {"script":"import os"},{"collectibles":[1.1]},
        ]:
            with self.subTest(fields=replacement):
                layout=deepcopy(scene["layout"]);layout.update(replacement)
                with self.assertRaises(SceneError):
                    make_advanced_scene("platformer",layout=layout)
        with self.assertRaises(SceneError):
            validate_advanced_scene(scene,{"gravity":4})
        with self.assertRaises(SceneError):
            make_advanced_scene("racing",layout={
                "corners":[5,5],"track_obstacle":7,"weather":"dry","starting_lane":0})


class SavegameTests(unittest.TestCase):
    def test_all_game_families_roundtrip_and_continue_without_state_trust(self):
        samples={
            "platformer":["jump_right","right"],
            "tactics":["east","end_turn"],
            "tower_defense":["build:0","tick:4"],
            "racing":["accelerate","coast"],
            "survival":["forage","drink"],
        }
        next_action={"platformer":"right","tactics":"end_turn",
                     "tower_defense":"tick","racing":"accelerate",
                     "survival":"rest"}
        for engine,actions in samples.items():
            with self.subTest(engine=engine):
                scene=make_advanced_scene(engine,seed=7)
                game=run_advanced_session(engine,actions=actions,seed=7,scene=scene)
                saved=export_advanced_savegame(game)
                restored=import_advanced_savegame(saved)
                self.assertTrue(restored["verified"])
                self.assertEqual(restored["session"],game)
                self.assertFalse(restored["external_code_executed"])
                resumed=continue_advanced_savegame(saved,[next_action[engine]])
                self.assertEqual(resumed["turns"],len(actions)+1)
                self.assertTrue(import_advanced_savegame(resumed)["verified"])
                self.assertEqual(resumed["actions"],actions+[next_action[engine]])
                self.assertNotEqual(saved["digest"],resumed["digest"])

    def test_independent_replay_detects_forged_gold_and_other_mutations(self):
        original=export_advanced_savegame(
            run_advanced_session("tower_defense",actions=["build:0","tick:4"]))
        for change in ("actions","session_digest","head_digest","settings",
                       "terminal","turns","scene"):
            with self.subTest(change=change):
                corrupted=deepcopy(original)
                if change=="actions":corrupted[change]=["build:1"]
                elif change=="settings":corrupted[change]["starting_credits"]=10000
                elif change=="scene":corrupted[change]={"cheat":True}
                elif change=="turns":corrupted[change]=77
                elif change=="terminal":corrupted[change]=True
                else:corrupted[change]="f"*64
                with self.assertRaises(SavegameError):
                    import_advanced_savegame(corrupted)
        forged=deepcopy(original)
        forged["actions"][0]="sell:0"
        forged.pop("digest")
        import hashlib
        raw=json.dumps(forged,sort_keys=True,separators=(",",":"),
                       ensure_ascii=True,allow_nan=False)
        forged["digest"]=hashlib.sha256(raw.encode()).hexdigest()
        with self.assertRaises(AdvancedRuntimeError):
            import_advanced_savegame(forged)

    def test_terminal_save_cannot_resurrect_dead_state(self):
        game=run_advanced_session("racing",{"track_length":20,"laps":1},
                                  actions=["accelerate"]*4)
        saved=export_advanced_savegame(game,{"track_length":20,"laps":1})
        self.assertTrue(import_advanced_savegame(saved)["session"]["terminal"])
        with self.assertRaises(AdvancedRuntimeError):
            continue_advanced_savegame(saved,["accelerate"])


class ReviewedSceneWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws=GameWorkspace.create(Path(self.tmp.name)/"work",authorized=True)
        self.ws.create_project("original_a","hybrid",authorized=True)

    def approve_system(self,engine,settings=None):
        source=editor_source(engine,settings)
        proposed=self.ws.propose("original_a","systems/"+engine+".json",source,
            expected_sha256=EMPTY_SHA,reason="Review canonical authored original game settings",
            authorized=True)
        self.ws.commit(proposed["proposal_id"],authorized=True,human_approved=True)

    def test_scene_requires_approved_system_and_exact_identity(self):
        scene=make_advanced_scene("platformer")
        path=scene_path(scene)
        content=json.dumps(scene)
        with self.assertRaises(WorkspaceError):
            self.ws.propose("original_a",path,content,expected_sha256=EMPTY_SHA,
                reason="Prevent unapproved scene from entering current product",
                authorized=True)
        self.approve_system("platformer")
        wrong="scenes/advanced_platformer_forged.json"
        with self.assertRaises(WorkspaceError):
            self.ws.propose("original_a",wrong,content,expected_sha256=EMPTY_SHA,
                reason="Reject mismatched original scene source paths",authorized=True)
        proposal=self.ws.propose("original_a",path,content,expected_sha256=EMPTY_SHA,
            reason="Review original authored hazard/checkpoint game layout",
            authorized=True)
        with self.assertRaises(PermissionError):
            self.ws.commit(proposal["proposal_id"],authorized=True,human_approved=False)
        self.ws.commit(proposal["proposal_id"],authorized=True,human_approved=True)
        self.assertEqual(json.loads(self.ws.read(
            "current","original_a",path)["content"]),scene)
        demo=self.ws.archive("original_a",authorized=True,demo=True)
        self.assertEqual(json.loads(self.ws.read(
            "demos",demo["ref"],path)["content"]),scene)

    def test_stale_scene_proposal_cannot_commit_after_system_changes(self):
        self.approve_system("platformer")
        scene=make_advanced_scene("platformer")
        proposal=self.ws.propose("original_a",scene_path(scene),json.dumps(scene),
            expected_sha256=EMPTY_SHA,
            reason="Stage scene before changing the referenced system",authorized=True)
        original=self.ws.read("current","original_a","systems/platformer.json")
        replacement=self.ws.propose("original_a","systems/platformer.json",
            editor_source("platformer",{"gravity":4}),
            expected_sha256=original["version"]["sha256"],
            reason="Update gravitational simulation before applying scene",authorized=True)
        self.ws.commit(replacement["proposal_id"],authorized=True,human_approved=True)
        with self.assertRaises(SceneError):
            self.ws.commit(proposal["proposal_id"],authorized=True,human_approved=True)


class SceneAndSaveAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws=GameWorkspace.create(Path(self.tmp.name)/"studio",authorized=True)
        self.ws.create_project("source","hybrid",authorized=True)
        self.server=create_workspace_server(self.ws,port=0)
        thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def post(self,route,data,token=True):
        conn=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=6)
        headers={"Content-Type":"application/json"}
        if token:headers["X-Game-Studio-Token"]=self.server.secret
        conn.request("POST",route,json.dumps(data),headers)
        result=conn.getresponse()
        status=result.status;body=json.loads(result.read())
        conn.close()
        return status,body

    def test_local_scene_prototype_and_save_restore(self):
        st,template=self.post("/api/advanced-scene-template",{
            "editor":"racing","seed":3,"scene_id":"first_race"})
        self.assertEqual(st,200)
        self.assertFalse(template["automatically_committed"])
        self.assertEqual(template["path"],"scenes/advanced_racing_first_race.json")
        self.assertFalse((self.ws.root/"current/source/scenes/advanced_racing_first_race.json").exists())
        st,game=self.post("/api/advanced-play",{
            "editor":"racing","seed":3,"scene":template["scene"],
            "actions":["accelerate","steer_right"]})
        self.assertEqual(st,200)
        self.assertTrue(game["session"]["scene_digest"])
        st,packed=self.post("/api/advanced-save",{"session":game["session"]})
        self.assertEqual(st,200)
        self.assertFalse(packed["source_project_mutated"])
        st,restored=self.post("/api/advanced-load",{"savegame":packed["savegame"]})
        self.assertEqual(st,200)
        self.assertEqual(restored["session"],game["session"])
        st,continued=self.post("/api/advanced-continue",{
            "savegame":packed["savegame"],"new_actions":["coast"]})
        self.assertEqual(st,200)
        self.assertEqual(continued["savegame"]["turns"],3)
        self.assertEqual(self.post("/api/advanced-load",{
            "savegame":{**packed["savegame"],"session_digest":"0"*64}})[0],400)
        self.assertEqual(self.post("/api/advanced-scene-template",{
            "editor":"racing"},token=False)[0],403)

    def test_visual_scene_and_savegame_controls_are_local(self):
        source=render_workspace_html("Z"*32).decode()
        for key in ('id="advanced-scene-template"','id="advanced-scene-stage"',
                    'id="advanced-scene-json"','id="advanced-save"',
                    'id="advanced-load"','Content-Security-Policy'):
            self.assertIn(key,source)
        self.assertNotIn("https://",source)

    def test_cli_scene_and_savegame_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(editor_cli(["scene-template","--editor","platformer"]),0)
            scene=json.loads(out.getvalue())
            path=Path(tmp)/"scene.json";path.write_text(json.dumps(scene))
            out=io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(editor_cli(["play","--editor","platformer",
                                             "--scene",str(path)]),0)
            game=json.loads(out.getvalue())
            receipt=Path(tmp)/"game.json";receipt.write_text(json.dumps(game))
            out=io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(editor_cli(["save","--session",str(receipt)]),0)
            saved=json.loads(out.getvalue())
            savepath=Path(tmp)/"save.json";savepath.write_text(json.dumps(saved))
            out=io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(editor_cli(["load-save","--savegame",str(savepath)]),0)
            self.assertTrue(json.loads(out.getvalue())["verified"])


if __name__=="__main__":
    unittest.main()
