"""Original living ecology: stable physical food webs and earned conservation."""
from __future__ import annotations
from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_ecosystem_runtime import (
    ACTIONS,GUILDS,HABITATS,EcosystemActionError,
    default_layout,normalize_layout,start,step,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    ACTION_HELP,ENGINES,AdvancedRuntimeError,
    run_advanced_session,verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    SceneError,make_advanced_scene,validate_advanced_scene,
)
from skeleton.ai.game_builder.system_editors import (
    catalog,make_editor_document,SystemEditorError,
)
from skeleton.ai.game_builder.system_editor_assembly import compile_system_assembly


class OriginalEcosystemTests(unittest.TestCase):
    def test_four_original_habitats_and_active_population_are_bounded(self):
        self.assertIn("ecosystem",ENGINES)
        self.assertEqual(set(ACTIONS),set(ACTION_HELP["ecosystem"]))
        spec=next(e for e in catalog() if e["id"]=="ecosystem")
        self.assertEqual(spec["runtime_maturity"],"advanced_reference_runtime")
        self.assertGreaterEqual(len(spec["fields"]),30)
        self.assertEqual(len(HABITATS),4)
        self.assertEqual(len(GUILDS),4)
        params={"species":500,"predators":100}
        game=run_advanced_session("ecosystem",params,["wait"]*2)
        self.assertEqual(game["state"]["species_total"],500)
        self.assertEqual(len(game["state"]["species"]),80)
        self.assertEqual(game["state"]["dormant_species"],420)
        self.assertTrue(verify_advanced_session(game,params))

    def test_ecological_scene_requires_exact_original_habitats(self):
        for seed in (0,1,2,9,31):
            config=make_editor_document("ecosystem")["settings"]
            original=default_layout(config,seed)
            self.assertEqual(normalize_layout(config,original),original)
            scene=make_advanced_scene("ecosystem",seed=seed)
            self.assertEqual(validate_advanced_scene(scene),scene)
            run=run_advanced_session("ecosystem",scene=scene,seed=seed)
            self.assertTrue(verify_advanced_session(run))
            self.assertFalse(run["native_hardware_verified"])

    def test_two_physical_surveys_and_real_restoration_earn_nonterminal_progress(self):
        actions=["survey","plant","east","north","survey","checkpoint"]
        proof=run_advanced_session("ecosystem",actions=actions)
        state=proof["state"]
        self.assertEqual(state["position"],[1,1])
        self.assertEqual(state["surveys"],[0,3])
        self.assertTrue(state["conservation_checkpoint"])
        self.assertFalse(state["finished"])
        self.assertFalse(state["failed"])
        self.assertEqual(state["plantings"],1)
        self.assertGreater(state["interventions"],0)
        self.assertTrue(verify_advanced_session(proof))
        end=run_advanced_session(
            "ecosystem",actions=actions+["west","south","retire"]
        )
        self.assertTrue(end["state"]["retired"])
        self.assertTrue(end["state"]["finished"])
        self.assertTrue(verify_advanced_session(end))

    def test_real_season_migration_food_and_reproduction_change_state(self):
        moving={"migration":True,"season_ticks":2,"migration_period":5}
        still={"migration":False,"season_ticks":2,"migration_period":5}
        migrant=run_advanced_session("ecosystem",moving,["wait"]*5)
        static=run_advanced_session("ecosystem",still,["wait"]*5)
        self.assertNotEqual(migrant["state"]["species"][0]["habitat"],
                            static["state"]["species"][0]["habitat"])
        self.assertGreater(migrant["state"]["migration_events"],0)
        self.assertEqual(static["state"]["migration_events"],0)
        self.assertEqual(migrant["state"]["season"],"autumn")
        self.assertTrue(verify_advanced_session(migrant,moving))
        self.assertTrue(verify_advanced_session(static,still))
        for site in migrant["state"]["habitats"]:
            self.assertGreaterEqual(site["food"],0)
            self.assertLessEqual(site["food"],site["capacity"])
        for kind in migrant["state"]["species"]:
            self.assertGreaterEqual(kind["population"],0)
            self.assertLessEqual(kind["population"],moving.get(
                "carrying_capacity",50
            ))

    def test_paid_protection_reduces_real_predation(self):
        settings={"migration":False,"hunt_period":5}
        without=run_advanced_session("ecosystem",settings,["wait"]*5)
        with_guard=run_advanced_session("ecosystem",settings,
                                        ["protect"]+["wait"]*4)
        self.assertLess(with_guard["state"]["predation_events"],
                        without["state"]["predation_events"])
        self.assertEqual(with_guard["state"]["credits"],37)
        self.assertTrue(verify_advanced_session(with_guard,settings))

    def test_wetland_outbreak_is_observable_and_finite_treatment_works(self):
        settings={"outbreak_period":2,"infection_rate":8}
        before=run_advanced_session("ecosystem",settings,["east","wait"])
        self.assertGreater(before["state"]["habitats"][1]["disease"],0)
        treated=run_advanced_session("ecosystem",settings,
                                     ["east","wait","treat"])
        self.assertEqual(treated["state"]["habitats"][1]["disease"],0)
        self.assertEqual(treated["state"]["medicine"],3)
        self.assertEqual(treated["state"]["treatments"],1)
        self.assertTrue(verify_advanced_session(treated,settings))
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("ecosystem",actions=["treat"])

    def test_finite_resources_and_direct_observations_are_enforced(self):
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("ecosystem",{"seed_bank":0},["plant"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("ecosystem",actions=["reintroduce"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("ecosystem",actions=["checkpoint"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("ecosystem",actions=["focus:15","observe"])
        result=run_advanced_session("ecosystem",actions=["observe"])
        self.assertEqual(result["state"]["observations"][0]["species"],0)
        self.assertTrue(verify_advanced_session(result))

    def test_scene_forgery_and_fake_wildlife_history_are_rejected(self):
        scene=make_advanced_scene("ecosystem")
        for attack in (
            lambda x:x["layout"]["habitats"][0].update(id=3),
            lambda x:x["layout"]["habitats"][3].update(capacity=100000),
            lambda x:x["layout"].update(critical_sites=[0]),
            lambda x:x["layout"].update(nonterminal=False),
            lambda x:x.update(digest="0"*64),
        ):
            bad=deepcopy(scene);attack(bad)
            with self.assertRaises(SceneError):
                validate_advanced_scene(bad)
        game=run_advanced_session("ecosystem",actions=["survey","plant"])
        bad=deepcopy(game)
        bad["state"]["species"][0]["population"]+=500
        with self.assertRaises(AdvancedRuntimeError):
            verify_advanced_session(bad)

    def test_authored_original_ecology_can_enter_hybrid_game_assembly(self):
        scene=make_advanced_scene("ecosystem")
        outcome=compile_system_assembly(
            "original_ecology",[make_editor_document("ecosystem")],
            authorized=True,scenes=[scene],
        )
        self.assertEqual(outcome["authored_scene_count"],1)
        self.assertEqual(outcome["advanced_runtime_evidence"][0]["editor"],
                         "ecosystem")

    def test_impossible_predator_or_population_ranges_fail_closed(self):
        for config in (
            {"species":2,"predators":4},
            {"initial_population":40,"carrying_capacity":5},
            {"predation_rate":True},
            {"minimum_living_population":500,"species":2,
             "carrying_capacity":5},
            {"reintroduction_population":50,"carrying_capacity":10},
            {"migration":"often"},
        ):
            with self.assertRaises(SystemEditorError):
                make_editor_document("ecosystem",config)


if __name__=="__main__":
    unittest.main()
