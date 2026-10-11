"""Cross-genre advanced gameplay reference: real actions, authored worlds and custody.

The three families are deliberately different: positional enemy combat, finite
turn-based deck decisions, and mode-specific puzzle objectives/rewind. No test
asserts a generic settings form is a production engine.
"""
from __future__ import annotations

from copy import deepcopy
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    ACTION_HELP, ENGINES, AdvancedRuntimeError,
    run_advanced_session, verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_genre_engines import CARDS
from skeleton.ai.game_builder.advanced_level_scenes import (
    SceneError, make_advanced_scene, validate_advanced_scene, scene_path,
)
from skeleton.ai.game_builder.advanced_gameplay_save import (
    SavegameError, export_advanced_savegame, import_advanced_savegame,
    continue_advanced_savegame,
)
from skeleton.ai.game_builder.system_editor_assembly import compile_system_assembly
from skeleton.ai.game_builder.system_editors import (
    ADVANCED_ENGINE_IDS, make_editor_document, catalog,
)
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html


class GenreMaturityTests(unittest.TestCase):
    def test_eight_genuine_advanced_replay_engines(self):
        self.assertEqual(set(ENGINES),set(ADVANCED_ENGINE_IDS))
        self.assertEqual(len(ENGINES),8)
        for genre in ("shooter","deck_battler","puzzle"):
            self.assertIn(genre,ACTION_HELP)
            self.assertGreaterEqual(len(ACTION_HELP[genre]),7)
        specs={spec["id"]:spec for spec in catalog()}
        self.assertEqual(len(specs),43)
        self.assertTrue(all(spec["progression_floor"]=="advanced" for spec in specs.values()))
        for genre in ENGINES:
            self.assertEqual(specs[genre]["runtime_maturity"],"advanced_reference_runtime")
        self.assertEqual(sum(1 for s in specs.values() if s["runtime_maturity"]=="authoring_only"),35)

    def test_distinct_reference_states_and_chain_identity(self):
        for genre,commands in (
            ("shooter",["wait","east","wait"]),
            ("deck_battler",["play:0","end_turn"]),
            ("puzzle",["east","undo","wait"]),
        ):
            with self.subTest(genre=genre):
                scene=make_advanced_scene(genre,seed=42)
                self.assertEqual(validate_advanced_scene(scene),scene)
                game=run_advanced_session(genre,actions=commands,seed=42,scene=scene)
                self.assertTrue(verify_advanced_session(game))
                self.assertEqual(len(game["trace"]),len(commands))
                self.assertEqual(game["trace"][0]["previous"],game["baseline_digest"])
                self.assertEqual(game["trace"][-1]["digest"],game["head_digest"])
                self.assertEqual(game["scene_digest"],scene["digest"])
                self.assertFalse(game["native_hardware_verified"])
                self.assertFalse(game["publication_certified"])
                altered=deepcopy(game);altered["state"]["finished"]=True
                with self.assertRaises(AdvancedRuntimeError):
                    verify_advanced_session(altered)


class ShooterGameplayTests(unittest.TestCase):
    def test_authoring_cover_line_of_sight_damage_and_medkits(self):
        settings={"enemy_count":4,"weapon_damage":2,"player_health":20}
        layout=make_advanced_scene("shooter",settings)["layout"]
        layout["player_spawn"]=[6,4]
        scene=make_advanced_scene("shooter",settings,layout=layout)
        game=run_advanced_session("shooter",settings,["fire","fire"],scene=scene)
        self.assertEqual(game["state"]["ammo"],10)
        self.assertGreater(game["state"]["score"],0)
        self.assertGreater(game["state"]["defeated"],0)
        self.assertTrue(verify_advanced_session(game,settings))
        self.assertEqual(game["scene"]["layout"]["player_spawn"],[6,4])
        blocked=deepcopy(layout)
        blocked["cover"]=[[7,y] for y in range(9)]
        with self.assertRaises(SceneError):
            make_advanced_scene("shooter",settings,layout=blocked)
        impossible=deepcopy(layout);impossible["player_spawn"]=[4,3]
        with self.assertRaises(SceneError):
            make_advanced_scene("shooter",settings,layout=impossible)

    def test_combat_resources_dodge_reloading_and_extraction_are_not_free(self):
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("shooter",actions=["fire"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("shooter",actions=["reload"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("shooter",actions=["medkit"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("shooter",actions=["extract"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("shooter",{"dodge_charges":0},actions=["dash:east"])
        moved=run_advanced_session("shooter",actions=["east","east"])
        self.assertEqual(moved["state"]["player"],[3,4])
        self.assertTrue(verify_advanced_session(moved))

    def test_shooter_scene_digests_bind_geometry_and_seed(self):
        source=make_advanced_scene("shooter",seed=1)
        adjusted=deepcopy(source);adjusted["layout"]["extraction"]=[13,5]
        with self.assertRaises(SceneError):
            validate_advanced_scene(adjusted)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("shooter",scene=source,seed=2)


class DeckBattlerTests(unittest.TestCase):
    def test_deck_consumes_energy_and_cards_and_enemies_act(self):
        cfg={"energy_per_turn":3,"attack_damage":6}
        layout=make_advanced_scene("deck_battler",cfg)["layout"]
        layout.update(cards=["strike"]*12,hand_size=3,
                      enemy_pattern=["attack","poison"],enemy_armor=0,potions=2)
        authored=make_advanced_scene("deck_battler",cfg,layout=layout)
        game=run_advanced_session("deck_battler",cfg,
                                  ["play:0","play:0","play:0","end_turn","potion"],
                                  scene=authored)
        state=game["state"]
        self.assertEqual(state["energy"],3)
        self.assertEqual(state["enemy_hp"],12)
        self.assertEqual(state["hp"],25)
        self.assertEqual(state["potions"],1)
        self.assertEqual(state["round"],2)
        self.assertEqual(state["enemy_intent"],"poison")
        self.assertTrue(verify_advanced_session(game,cfg))
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("deck_battler",cfg,
                                 ["play:0","play:0","play:0","play:0"],scene=authored)

    def test_deck_completion_and_illegal_custom_source(self):
        cfg={"enemy_health":5,"attack_damage":10}
        layout=make_advanced_scene("deck_battler",cfg)["layout"]
        layout["cards"]=["strike"]*12
        scene=make_advanced_scene("deck_battler",cfg,layout=layout)
        game=run_advanced_session("deck_battler",cfg,["play:0"],scene=scene)
        self.assertTrue(game["terminal"])
        self.assertTrue(game["state"]["finished"])
        self.assertEqual(game["state"]["enemy_hp"],0)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("deck_battler",cfg,["play:0","end_turn"],scene=scene)
        invalid=deepcopy(layout);invalid["cards"]=["unknown"]*12
        with self.assertRaises(SceneError):
            make_advanced_scene("deck_battler",cfg,layout=invalid)
        invalid=deepcopy(layout);invalid["cards"]=["guard"]*12
        with self.assertRaises(SceneError):
            make_advanced_scene("deck_battler",cfg,layout=invalid)


class PuzzleGameplayTests(unittest.TestCase):
    def test_switch_puzzle_requires_objective_and_can_be_won(self):
        cfg={"board_width":4,"board_height":4}
        scene=make_advanced_scene("puzzle",cfg)
        path=["east","interact","east","east","south","south","south"]
        game=run_advanced_session("puzzle",cfg,path,scene=scene)
        self.assertTrue(game["state"]["finished"])
        self.assertIn([1,0],game["state"]["switches_on"])
        self.assertEqual(game["state"]["player"],[3,3])
        self.assertTrue(verify_advanced_session(game,cfg))
        prior=run_advanced_session("puzzle",cfg,["east","undo"],scene=scene)
        self.assertEqual(prior["state"]["player"],[0,0])
        self.assertEqual(prior["state"]["undo_available"],31)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("puzzle",cfg,["undo"],scene=scene)

    def test_push_block_and_non_euclidean_are_distinct_real_modes(self):
        cfg={"logic":"push_blocks","board_width":4,"board_height":4}
        scene=make_advanced_scene("puzzle",cfg)
        game=run_advanced_session("puzzle",cfg,
                ["south","east","south","east","east","south"],scene=scene)
        self.assertTrue(game["state"]["finished"])
        self.assertEqual(game["state"]["crates"],[[2,1]])
        self.assertTrue(verify_advanced_session(game,cfg))
        portal_cfg={"logic":"non_euclidean","board_width":4,"board_height":4}
        portal=make_advanced_scene("puzzle",portal_cfg)
        result=run_advanced_session("puzzle",portal_cfg,["east","east"],scene=portal)
        self.assertTrue(result["state"]["portal_visited"])
        self.assertTrue(result["state"]["finished"])
        self.assertIn("portal_traversed",result["trace"][0]["events"])

    def test_circuits_and_time_have_distinct_objectives(self):
        cfg={"logic":"circuits","board_width":4,"board_height":4}
        scene=make_advanced_scene("puzzle",cfg)
        game=run_advanced_session("puzzle",cfg,
                ["east","interact","south","interact","east","east","south","south"],
                scene=scene)
        self.assertTrue(game["state"]["finished"])
        self.assertEqual(len(game["state"]["powered_nodes"]),2)
        cfg_time={"logic":"time","board_width":4,"board_height":4}
        clock=run_advanced_session("puzzle",cfg_time,["wait","wait"],
                                   scene=make_advanced_scene("puzzle",cfg_time))
        self.assertEqual(clock["state"]["phase"],0)
        self.assertIn("phase_shift",clock["trace"][0]["events"])

    def test_compact_puzzles_and_disconnected_authored_geometry(self):
        for logic in ("switches","push_blocks","circuits","time","non_euclidean"):
            with self.subTest(logic=logic):
                cfg={"logic":logic,"board_width":3,"board_height":3}
                scene=make_advanced_scene("puzzle",cfg)
                self.assertTrue(verify_advanced_session(
                    run_advanced_session("puzzle",cfg,["wait"],scene=scene),cfg))
        cfg={"board_width":4,"board_height":4}
        original=make_advanced_scene("puzzle",cfg)["layout"]
        original["walls"]=[[2,0],[2,1],[2,2],[2,3]]
        with self.assertRaises(SceneError):
            make_advanced_scene("puzzle",cfg,layout=original)


class CrossCuttingCustodyTests(unittest.TestCase):
    def test_new_genres_share_real_save_restore_and_continue(self):
        commands={"shooter":["wait"],"deck_battler":["play:0"],"puzzle":["wait"]}
        next_action={"shooter":"east","deck_battler":"end_turn","puzzle":"east"}
        for engine in commands:
            with self.subTest(engine=engine):
                scene=make_advanced_scene(engine,seed=5)
                game=run_advanced_session(engine,actions=commands[engine],seed=5,scene=scene)
                saved=export_advanced_savegame(game)
                self.assertEqual(import_advanced_savegame(saved)["session"],game)
                extended=continue_advanced_savegame(saved,[next_action[engine]])
                self.assertEqual(extended["turns"],2)
                self.assertTrue(import_advanced_savegame(extended)["verified"])
                tampered=deepcopy(saved);tampered["actions"]=["hack"]
                with self.assertRaises(SavegameError):
                    import_advanced_savegame(tampered)

    def test_authored_scenes_produce_evidence_in_compiled_hybrid(self):
        for genre in ("shooter","deck_battler","puzzle"):
            with self.subTest(genre=genre):
                source=make_editor_document(genre)
                scene=make_advanced_scene(genre)
                built=compile_system_assembly("original_campaign",[source],
                                              scenes=[scene],authorized=True)
                self.assertEqual(built["authored_scene_count"],1)
                self.assertEqual(built["authored_scene_evidence"][0]["scene_digest"],
                                 scene["digest"])
                self.assertEqual(len(built["advanced_runtime_evidence"]),1)
                self.assertFalse(built["ready_for_release"])


class StudioSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        ws=GameWorkspace.create(Path(self.temp.name)/"game",authorized=True)
        ws.create_project("original_multi","hybrid",authorized=True)
        self.server=create_workspace_server(ws,port=0)
        t=threading.Thread(target=self.server.serve_forever,daemon=True)
        t.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def post(self,path,payload,token=True):
        conn=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=5)
        headers={"Content-Type":"application/json"}
        if token:
            headers["X-Game-Studio-Token"]=self.server.secret
        conn.request("POST",path,json.dumps(payload),headers)
        res=conn.getresponse();code=res.status
        body=json.loads(res.read());conn.close()
        return code,body

    def test_headless_live_play_save_and_actions_after_import(self):
        for genre in ("shooter","deck_battler","puzzle"):
            with self.subTest(genre=genre):
                status,generated=self.post("/api/advanced-scene-template",
                        {"editor":genre,"seed":2})
                self.assertEqual(status,200)
                self.assertFalse(generated["automatically_committed"])
                status,played=self.post("/api/advanced-play",{
                    "editor":genre,"scene":generated["scene"],
                    "seed":2,"actions":[]})
                self.assertEqual(status,200)
                status,serialized=self.post("/api/advanced-save",{
                    "session":played["session"]})
                self.assertEqual(status,200)
                status,restored=self.post("/api/advanced-load",{
                    "savegame":serialized["savegame"]})
                self.assertEqual(status,200)
                self.assertEqual(set(restored["available_actions"]),
                                 set(ACTION_HELP[genre]))
                self.assertEqual(self.post("/api/advanced-play",{
                    "editor":genre,"seed":2,"actions":[]},
                    token=False)[0],403)
        html=render_workspace_html("X"*32).decode()
        for genre in ("shooter","deck battler","puzzle"):
            self.assertIn(genre,html)


if __name__=="__main__":
    unittest.main()
