"""Functional acceptance for 4,500 compiled, executable game-production recipes.

A recipe is an actual multi-step typed StudioProject transaction, not a label,
gate or mock. Check all names and plans, execute representative actions across
all ten domains/nine treatments and 500 source blueprints, round-trip game
content, verify quest DAG/NPC linkage/environment proposals/native output.
"""
from __future__ import annotations

import unittest

from skeleton.forge.game_frontier_studio import (
    StudioError, StudioProject, compile_studio_native_quest_graph,
    compile_studio_expedition,
)
from skeleton.forge.game_frontier_rpg_events import evaluate_environment_events
from skeleton.forge.game_frontier_studio_authoring import (
    AUTHORING_ACTIONS, apply_authoring_batch, authored_summary,
    execute_authoring, project_digest,
)
from skeleton.forge.game_frontier_studio_production_recipes import (
    RECIPE_ACTIONS, RECIPE_INDEX, TREATMENTS, describe_recipe,
    search_recipes,
)
from skeleton.forge.game_frontier_studio_document import (
    authored_document, load_authored_document,
)
from skeleton.testing.test_game_frontier_studio_authoring_500 import original_project


def arguments(action: str) -> dict:
    return {
        "layer": "biome", "x": 0, "y": 0, "width": 16, "height": 16,
        "floor": 0, "wall": 1, "seed": 43, "scale": 5, "threshold": .53,
        "prefab_id": "merchant", "count": 4, "radius": 6, "spacing": 2,
        "z": 0,
    }


class ForgeFiveThousandRealProducers(unittest.TestCase):
    def test_all_5000_game_producers_have_stable_unique_registry(self):
        self.assertEqual(5000, len(AUTHORING_ACTIONS))
        self.assertEqual(5000, len(set(AUTHORING_ACTIONS)))
        self.assertEqual(4500, len(RECIPE_ACTIONS))
        self.assertEqual(4500, len(RECIPE_INDEX))
        self.assertEqual(RECIPE_ACTIONS, AUTHORING_ACTIONS[500:])

    def test_all_4500_actions_compile_to_real_source_bound_plans(self):
        seen=set()
        groups={}
        for action in RECIPE_ACTIONS:
            recipe=describe_recipe(action)
            key=(recipe["domain"], recipe["source_index"], recipe["treatment"])
            self.assertNotIn(key, seen)
            seen.add(key)
            self.assertIn(recipe["style_index"], range(9))
            self.assertTrue(1<=len(recipe["recipe_steps"])<=2)
            self.assertTrue(recipe["actual_project_mutation"])
            groups[recipe["domain"]]=groups.get(recipe["domain"],0)+1
        self.assertEqual(10,len(groups))
        self.assertTrue(all(n==450 for n in groups.values()))
        self.assertEqual(4500,len(seen))

    def test_every_base_blueprint_changes_actual_game_source(self):
        original=original_project()
        digest=project_digest(original)
        # Each of 500 distinct authored blueprints must execute at least one
        # 9-treatment production recipe and mutate typed persistent source.
        for group in range(10):
            for blueprint in range(50):
                action=RECIPE_ACTIONS[(group*50+blueprint)*9]
                with self.subTest(recipe=action):
                    changed=execute_authoring(original,action,arguments(action))
                    self.assertIsInstance(changed, StudioProject)
                    self.assertNotEqual(digest,project_digest(changed))
                    self.assertEqual(original.project_id,changed.project_id)
        self.assertEqual(digest,project_digest(original))

    def test_all_nine_treatments_change_real_source_in_every_domain(self):
        original=original_project()
        for domain in range(10):
            digest_by_treatment=set()
            for style in range(9):
                action=RECIPE_ACTIONS[domain*450+style]
                with self.subTest(domain=domain,style=TREATMENTS[style]):
                    changed=execute_authoring(original,action,arguments(action))
                    digest_by_treatment.add(project_digest(changed))
                    self.assertNotEqual(project_digest(original),project_digest(changed))
            # Source geometries, NPC positions, quest branches and sensor
            # conditions MUST be distinct for all nine treatments.
            self.assertEqual(9,len(digest_by_treatment))

    def test_search_is_bounded_and_stably_paginated(self):
        first=search_recipes(query="sky",offset=0,limit=16)
        second=search_recipes(query="sky",offset=16,limit=16)
        self.assertEqual(4500,first["total_catalog"])
        self.assertLessEqual(len(first["items"]),16)
        self.assertFalse({item["operation"] for item in first["items"]} &
                         {item["operation"] for item in second["items"]})
        domain=search_recipes(domain="living_story",offset=0,limit=7)
        self.assertEqual(450,domain["matched"])
        self.assertEqual(7,len(domain["items"]))
        with self.assertRaises(StudioError):
            search_recipes(limit=1000)
        with self.assertRaises(StudioError):
            describe_recipe("produce_unapproved_unknown__secrets")

    def test_build_world_settlement_npcs_quest_environment_as_one_transaction(self):
        base=original_project()
        selected=[
            RECIPE_ACTIONS[5*450+1],
            RECIPE_ACTIONS[7*450+14],
            RECIPE_ACTIONS[8*450+23],
            RECIPE_ACTIONS[9*450+34],
        ]
        # Unique generated source identities are guaranteed by each operation
        # name, with no reliance on fixture state or external provider.
        change=apply_authoring_batch(base,[
            {"action":name,"parameters":arguments(name)} for name in selected
        ])
        revised=change["project"]
        self.assertEqual(4,change["receipt"]["action_count"])
        self.assertGreater(len(revised.placements),len(base.placements))
        self.assertGreater(len(revised.native_quests),len(base.native_quests))
        self.assertGreater(len(revised.environmental_pages),len(base.environmental_pages))
        self.assertNotEqual(project_digest(base),project_digest(revised))
        reopened=load_authored_document(
            authored_document(revised), project_id=base.project_id)
        self.assertEqual(project_digest(revised),project_digest(reopened))
        self.assertEqual(revised.placements,reopened.placements)
        self.assertEqual(revised.native_quests,reopened.native_quests)
        self.assertEqual(revised.environmental_pages,reopened.environmental_pages)
        graph=compile_studio_native_quest_graph(reopened)
        self.assertGreaterEqual(len(graph["quests"]),2)
        self.assertEqual(project_digest(base),project_digest(original_project()))

    def test_composed_encounter_actor_events_link_to_real_placements(self):
        original=original_project()
        recipe=RECIPE_ACTIONS[2*450+31]
        made=execute_authoring(original,recipe,arguments(recipe))
        actors=made.placements[len(original.placements):]
        events=made.events[len(original.events):]
        self.assertEqual(4,len(actors))
        self.assertEqual(4,len(events))
        self.assertEqual(
            {f"merchant:{len(original.placements)+j}" for j in range(4)},
            {event.target for event in events}
        )

    def test_composed_environmental_sensor_adds_actual_third_condition(self):
        original=original_project()
        recipe=RECIPE_ACTIONS[4*450+4]
        made=execute_authoring(original,recipe,arguments(recipe))
        page=made.environmental_pages[-1]
        self.assertEqual(3,len(page.conditions))
        self.assertEqual("show_dialogue",page.actions[0].kind)
        conditions={c.signal:c for c in page.conditions}
        self.assertIn("party_morale",conditions)

    def test_transaction_never_partially_persists_failed_recipe(self):
        base=original_project()
        original_hash=project_digest(base)
        action=RECIPE_ACTIONS[6*450]
        with self.assertRaises(StudioError):
            apply_authoring_batch(base,[
                {"action":action,"parameters":arguments(action)},
                {"action":"produce_untrusted_code__secret",
                 "parameters":{"seed":42}},
            ])
        self.assertEqual(original_hash,project_digest(base))

    def test_large_catalog_summary_does_not_send_4500_names_per_edit(self):
        summary=authored_summary(original_project())
        self.assertEqual(500,len(summary["action_catalog"]))
        self.assertEqual(4500,summary["recipe_catalog_count"])
        self.assertEqual(5000,summary["catalog_total"])
        self.assertTrue(summary["recipe_search_required"])

    def test_godot_world_compiler_consumes_composed_production_recipe(self):
        from skeleton.jeeves.game_frontier_expedition_generation import ArchipelagoProfile
        original=original_project()
        action=RECIPE_ACTIONS[5*450+9]
        authored=execute_authoring(original,action,arguments(action))
        build=compile_studio_expedition(
            authored,
            ArchipelagoProfile(seed=27,islands=4,caverns=0,
                               include_portals=False,include_underwater=False),
            playtest_routes=2,include_godot=True,
        )
        self.assertIn("game/frontier/studio_terrain.gd",build["godot_project_files"])
        self.assertIn("game/frontier/studio_terrain.json",build["godot_project_files"])
        self.assertGreater(build["travel_edges"],0)


if __name__=="__main__":
    unittest.main()
