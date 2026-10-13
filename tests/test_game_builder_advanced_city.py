"""Original urban game functionality, spatial supply and review-chain regressions."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_city_runtime import (
    ACTIONS, PARCELS, CityActionError, default_layout, normalize_layout,
    neighbors,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    ENGINES, AdvancedRuntimeError, run_advanced_session, verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    SceneError, make_advanced_scene, validate_advanced_scene,
)
from skeleton.ai.game_builder.advanced_gameplay_save import (
    export_advanced_savegame, import_advanced_savegame, continue_advanced_savegame,
)
from skeleton.ai.game_builder.system_editor_assembly import compile_system_assembly
from skeleton.ai.game_builder.system_editors import make_editor_document, catalog


class AdvancedOriginalCityGameTests(unittest.TestCase):
    def test_city_is_a_real_advanced_editor_with_typed_game_configuration(self):
        self.assertIn("city_builder", ENGINES)
        self.assertEqual(len(make_editor_document("city_builder")["settings"]),15)
        self.assertGreater(len(ACTIONS),100)
        spec=next(s for s in catalog() if s["id"]=="city_builder")
        self.assertEqual(spec["runtime_maturity"],"advanced_reference_runtime")
        self.assertEqual(spec["progression_floor"],"advanced")

    def test_road_graph_blocks_disconnected_zoning_and_legal_city_prosperity(self):
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("city_builder", actions=["build:residential:15"])
        actions=["build:road:1","build:road:2","build:road:4","build:road:8",
                 "build:residential:5","build:commercial:6","build:power:3",
                 "build:waterworks:9","tick:4"]
        city=run_advanced_session("city_builder",actions=actions,seed=0)
        self.assertTrue(verify_advanced_session(city))
        self.assertGreaterEqual(city["state"]["population"],12)
        self.assertGreaterEqual(city["state"]["employment"],8)
        self.assertTrue(city["state"]["powered"])
        self.assertTrue(city["state"]["watered"])
        self.assertIn("functioning_original_city",city["state"]["milestones"])
        self.assertFalse(city["terminal"]) # meaningful post-completion play
        self.assertLess(city["state"]["aquifer"],80)
        self.assertLess(city["state"]["wood"],55)
        self.assertTrue(any("connected_zones_attract_actual_residents" in item["events"]
                            for item in city["trace"]))

    def test_native_terrain_is_conserved_in_development_and_resource_extraction(self):
        settings=make_editor_document("city_builder")["settings"]
        layout=default_layout(settings,0)
        self.assertEqual(len(layout["terrain"]),PARCELS)
        self.assertIn(1,neighbors(0))
        self.assertNotIn(5,neighbors(0))
        scene=make_advanced_scene("city_builder",seed=0)
        actions=["log:5","log:5","quarry:6"]
        state=run_advanced_session("city_builder",actions=actions,scene=scene)["state"]
        self.assertEqual(state["timber_reserve"],layout["timber_reserve"]-12)
        self.assertEqual(state["stone_reserve"],layout["stone_reserve"]-6)
        self.assertEqual(state["wood"],55+12)
        self.assertEqual(state["stone"],45+6)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("city_builder",actions=["quarry:5"],scene=scene)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("city_builder",actions=["build:road:15"],scene=scene)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("city_builder",actions=["build:bridge:1"],scene=scene)

    def test_utility_service_is_not_fabricated_and_water_is_finite(self):
        actions=["build:road:1","build:road:2","build:road:4",
                 "build:residential:5","build:commercial:6"]
        disconnected=run_advanced_session("city_builder",actions=actions+["tick:4"])
        self.assertEqual(disconnected["state"]["population"],0)
        self.assertFalse(disconnected["state"]["powered"])
        self.assertFalse(disconnected["state"]["watered"])
        scene=make_advanced_scene("city_builder",layout={
            **default_layout(make_editor_document("city_builder")["settings"],0),
            "aquifer":2,
        })
        with_supply=run_advanced_session(
            "city_builder",actions=actions+["build:road:8","build:power:3","build:waterworks:9",
                                    "tick:4"],scene=scene)
        self.assertLessEqual(with_supply["state"]["population"],2)
        self.assertGreaterEqual(with_supply["state"]["aquifer"],0)

    def test_policy_and_traffic_and_tax_change_actual_play(self):
        initial=["build:road:1","build:road:2","build:road:4","build:road:8",
                 "build:residential:5","build:commercial:6","build:power:3",
                 "build:waterworks:9"]
        a=run_advanced_session("city_builder",{"road_capacity":1},
                               initial+["tax:low","tick:4"])["state"]
        b=run_advanced_session("city_builder",{"road_capacity":1},
                               initial+["tax:high","tick:4"])["state"]
        self.assertLess(a["credits"],b["credits"])
        self.assertGreater(a["happiness"],b["happiness"])
        c=run_advanced_session("city_builder",{"road_capacity":1},
                               initial+["policy:industrial","tick:4"])["state"]
        self.assertGreaterEqual(c["congestion"],a["congestion"])

    def test_scene_rejects_untrusted_grid_and_identifies_author(self):
        cfg={"road_capacity":12}
        source=make_advanced_scene("city_builder",cfg,seed=3)
        self.assertEqual(validate_advanced_scene(source,cfg),source)
        for mutation in (
            lambda x:x["layout"].update(road_hub=15),
            lambda x:x["layout"]["terrain"].append("plain"),
            lambda x:x["layout"]["terrain"].__setitem__(1,"imported_level"),
            lambda x:x["layout"].update(injected_python="exec()"),
            lambda x:x["layout"].update(aquifer=True),
            lambda x:x.update(seed=4),
            lambda x:x.update(digest="0"*64),
        ):
            changed=deepcopy(source)
            mutation(changed)
            with self.assertRaises((SceneError,CityActionError)):
                validate_advanced_scene(changed,cfg)
        with self.assertRaises(SceneError):
            validate_advanced_scene(source,{"road_capacity":11})

    def test_receipts_saves_forgeries_and_hybrid_are_validated(self):
        cfg={"opening_budget":600}
        scene=make_advanced_scene("city_builder",cfg,seed=2)
        original=run_advanced_session("city_builder",cfg,
                       ["build:road:1","build:residential:5","tick"],
                       seed=2,scene=scene)
        self.assertTrue(verify_advanced_session(original,cfg))
        save=export_advanced_savegame(original,cfg)
        self.assertEqual(import_advanced_savegame(save)["session"],original)
        resumed=continue_advanced_savegame(save,["build:commercial:2"])
        self.assertTrue(import_advanced_savegame(resumed)["verified"])
        for k,value in (("credits",999999),("population",5000),("finished",True)):
            forged=deepcopy(original)
            forged["state"][k]=value
            with self.assertRaises(AdvancedRuntimeError):
                verify_advanced_session(forged,cfg)
        assembly=compile_system_assembly("urban_hybrid",
                        [make_editor_document("city_builder",cfg)],
                        authorized=True,scenes=[scene])
        self.assertEqual(assembly["authored_scene_count"],1)
        self.assertEqual(assembly["advanced_runtime_evidence"][0]["editor"],"city_builder")
        self.assertEqual(assembly["authored_scene_evidence"][0]["editor"],"city_builder")
        self.assertFalse(assembly["ready_for_release"])

    def test_visual_city_authoring_and_urban_command_composer(self):
        from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html, SCRIPT
        page=render_workspace_html("A"*32).decode("utf-8")
        for piece in ("paintCityCell","terrain_plain","aquifer_plus",
                      "road_hub","city-target-cell","city-registered-action",
                      "Issue verified city order","function drawAdvancedGame"):
            self.assertIn(piece,page)
        self.assertIn("City geography changed",SCRIPT)
        self.assertIn("selectedCityParcel",SCRIPT)
        # Draft source cannot bypass the Studio scene validation.
        scene=make_advanced_scene("city_builder",seed=5)
        changed=deepcopy(scene)
        changed["layout"]["terrain"][1]="forest"
        with self.assertRaises(SceneError):
            validate_advanced_scene(changed)
        signed=make_advanced_scene("city_builder",seed=5,layout=changed["layout"])
        self.assertNotEqual(scene["digest"],signed["digest"])
        self.assertTrue(verify_advanced_session(
            run_advanced_session("city_builder",seed=5,scene=signed)))

    def test_original_urban_cli_emits_gameplay_without_hidden_project_writes(self):
        import io, json
        from contextlib import redirect_stdout
        from skeleton.ai.game_builder.system_editor_cli import main
        output=io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["play","--editor","city_builder","--seed","5"]),0)
        session=json.loads(output.getvalue())
        self.assertTrue(verify_advanced_session(session))
        self.assertFalse(session["native_hardware_verified"])
        self.assertFalse(session["publication_certified"])
        self.assertEqual(session["state"]["day"],1)

    def test_budget_debt_damage_and_policy_constrain_cheats(self):
        for illegal in ("build:park:999","materialize:free",
                        "tax:infinite","bridge:teleport"):
            with self.assertRaises(AdvancedRuntimeError):
                run_advanced_session("city_builder",actions=[illegal])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("city_builder",actions=["bond"]*5)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("city_builder",actions=["pay_debt"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("city_builder",actions=["tick"]*129)
        low={"opening_budget":50}
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("city_builder",low,
                actions=["build:road:1","build:residential:5","build:road:2",
                         "build:commercial:6","build:power:3"])


if __name__=="__main__":
    unittest.main()
