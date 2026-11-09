"""Original RPG: tactical party, witnessed choices, earned chapters and replay."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_rpg_runtime import (
    ACTIONS,CLASSES,QUESTS,RPGActionError,
    default_layout,normalize_layout,start,step,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    ENGINES,ACTION_HELP,AdvancedRuntimeError,
    run_advanced_session,verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    SceneError,make_advanced_scene,validate_advanced_scene,
)
from skeleton.ai.game_builder.system_editors import (
    catalog,make_editor_document,SystemEditorError,
)
from skeleton.ai.game_builder.system_editor_assembly import compile_system_assembly


def earned_story_actions():
    return [
        "north","accept","east","east","east","east","investigate","gather",
        "west","north","north","attack","attack",
        "west","north","north","negotiate",
        "west","south","south","south","south","turn_in",
        "east","east","north","north","east","east",
        "north","north","north","north","east","east","finish",
    ]


class OriginalRPGTests(unittest.TestCase):
    def test_rpg_is_real_advanced_game_not_editor_only(self):
        self.assertIn("rpg",ENGINES)
        self.assertEqual(set(ACTIONS),set(ACTION_HELP["rpg"]))
        self.assertEqual(len(ACTIONS),len(set(ACTIONS)))
        spec=next(s for s in catalog() if s["id"]=="rpg")
        self.assertEqual(spec["runtime_maturity"],"advanced_reference_runtime")
        self.assertGreaterEqual(len(spec["fields"]),35)
        self.assertEqual(len(CLASSES),4)
        self.assertEqual(set(QUESTS),{"recover_relic","resolve_dispute","clear_threat"})

    def test_original_worlds_are_custodied_and_independently_replayed(self):
        for seed in (0,1,2,19):
            settings=make_editor_document("rpg")["settings"]
            layout=default_layout(settings,seed)
            self.assertEqual(normalize_layout(settings,layout),layout)
            scene=make_advanced_scene("rpg",seed=seed)
            self.assertEqual(validate_advanced_scene(scene),scene)
            receipt=run_advanced_session("rpg",scene=scene,seed=seed)
            self.assertTrue(verify_advanced_session(receipt))
            self.assertFalse(receipt["native_hardware_verified"])

    def test_full_witnessed_three_quest_story_can_complete_and_continue(self):
        actions=earned_story_actions()
        proof=run_advanced_session("rpg",actions=actions)
        state=proof["state"]
        self.assertEqual(state["chapters_completed"],1)
        self.assertTrue(state["chapter_claimed"])
        self.assertFalse(state["finished"])
        self.assertFalse(state["failed"])
        self.assertEqual(state["position"],[7,7])
        self.assertEqual(set(state["quests"].values()),{"completed"})
        self.assertEqual(state["inventory"]["relic"],1)
        self.assertEqual(state["enemy_hp"],0)
        self.assertEqual(state["factions"]["village"],3)
        self.assertGreater(state["party"][0]["level"],1)
        self.assertTrue(any(m["subject"]=="trust" for m in state["social_memories"]))
        self.assertTrue(verify_advanced_session(proof))
        aftermath=run_advanced_session("rpg",actions=actions+["west","retire"])
        self.assertTrue(aftermath["state"]["finished"])
        self.assertGreater(aftermath["state"]["postgame_steps"],0)
        self.assertTrue(verify_advanced_session(aftermath))

    def test_story_may_end_or_continue_per_editor_source_choice(self):
        params={"persistent_world":False}
        proof=run_advanced_session("rpg",params,earned_story_actions())
        self.assertTrue(proof["state"]["finished"])
        self.assertEqual(proof["state"]["chapters_completed"],1)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("rpg",params,earned_story_actions()+["west"])

    def test_party_class_specialization_has_real_resource_and_damage_effects(self):
        cfg=make_editor_document("rpg")["settings"]
        guardian=start(cfg,0);scholar=start(cfg,0)
        for game in (guardian,scholar):
            game["position"]=[3,3]
        step(guardian,cfg,"attack")
        step(scholar,cfg,"select:1")
        step(scholar,cfg,"cast")
        self.assertNotEqual(guardian["enemy_hp"],scholar["enemy_hp"])
        self.assertLess(scholar["party"][1]["mana"],cfg["hero_mana"])
        scout=start(cfg,0);scout["position"]=[4,1]
        step(scout,cfg,"select:2")
        step(scout,cfg,"investigate")
        self.assertEqual(scout["inventory"]["ore"],1)
        self.assertEqual(scout["evidence"],["ruin_survey"])

    def test_quest_rewards_cannot_be_minted_outside_actual_events(self):
        for commands in (
            ["turn_in"],["finish"],["retire"],
            ["attack"],["cast"],["choose:trust"],
            ["east","east","east","east","gather"],
        ):
            with self.assertRaises(AdvancedRuntimeError):
                run_advanced_session("rpg",actions=commands)
        with self.assertRaises(RPGActionError):
            step(start(make_editor_document("rpg")["settings"],0),
                 make_editor_document("rpg")["settings"],"teleport_world")

    def test_spoofed_npcs_world_map_and_xp_evidence_rejected(self):
        scene=make_advanced_scene("rpg")
        for edit in (
            lambda s:s["layout"]["npcs"][0].update(id=7),
            lambda s:s["layout"]["npcs"][1].update(role="owner"),
            lambda s:s["layout"].update(exit=[2,2]),
            lambda s:s["layout"].update(quests=[]),
            lambda s:s.update(digest="f"*64),
        ):
            bad=deepcopy(scene);edit(bad)
            with self.assertRaises(SceneError):
                validate_advanced_scene(bad)
        proof=run_advanced_session("rpg",actions=["north","accept"])
        bad=deepcopy(proof)
        bad["state"]["party"][0]["xp"]=9999
        with self.assertRaises(AdvancedRuntimeError):
            verify_advanced_session(bad)

    def test_authored_rpg_can_be_assembled_with_live_source_proof(self):
        spec=make_editor_document("rpg")
        scene=make_advanced_scene("rpg")
        result=compile_system_assembly("original_rpg",[spec],
                                      authorized=True,scenes=[scene])
        self.assertEqual(result["authored_scene_count"],1)
        self.assertEqual(result["advanced_runtime_evidence"][0]["editor"],"rpg")

    def test_invalid_configuration_cannot_bypass_resource_bounds(self):
        for config in (
            {"party_size":17},{"hero_health":True},
            {"starting_herbs":20,"herb_capacity":2},
            {"hero_mana":0,"spell_cost":8},
            {"world_width":8,"max_obstacles":64},
            {"persistent_world":"yes"},
            {"quest_depth":129},
        ):
            with self.assertRaises(SystemEditorError):
                make_editor_document("rpg",config)


if __name__=="__main__":
    unittest.main()
