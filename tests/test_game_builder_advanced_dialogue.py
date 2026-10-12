"""31st original playable game family: spatial, causal, replayed dialogue."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.system_editors import (
    ADVANCED_ENGINE_IDS, catalog, make_editor_document,
)
from skeleton.ai.game_builder.advanced_dialogue_runtime import (
    ACTIONS, DialogueActionError, LOCATIONS, default_layout, normalize_layout,
    start, step,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    ACTION_HELP, ENGINES, AdvancedRuntimeError, run_advanced_session,
    verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    SceneError, make_advanced_scene, validate_advanced_scene,
)
from skeleton.ai.game_builder.system_editor_assembly import compile_system_assembly

CONSENSUS = ("speak:0", "support:0", "travel:1", "speak:4",
             "travel:2", "compare:0", "claim")


class OriginalAdvancedDialogueTests(unittest.TestCase):
    def test_advanced_dialogue_is_playable_with_more_than_authoring_only_metadata(self):
        self.assertIn("dialogue", ENGINES)
        self.assertIn("dialogue", ADVANCED_ENGINE_IDS)
        self.assertEqual(tuple(ACTION_HELP["dialogue"]), ACTIONS)
        item = next(row for row in catalog() if row["id"] == "dialogue")
        self.assertEqual(item["runtime_maturity"], "advanced_reference_runtime")
        self.assertGreaterEqual(len(item["fields"]), 21)
        self.assertIn("speaker_patience", {x["key"] for x in item["fields"]})
        self.assertIn("dialogue_turn_budget", {x["key"] for x in item["fields"]})

    def test_real_earned_corroborated_consensus_and_optional_epilogue(self):
        scene = make_advanced_scene("dialogue", seed=2)
        output = run_advanced_session("dialogue", actions=CONSENSUS,
                                      seed=2, scene=scene)
        self.assertTrue(verify_advanced_session(output))
        final = output["state"]
        self.assertTrue(final["checkpoint"])
        self.assertFalse(final["finished"])
        self.assertFalse(final["retired"])
        self.assertEqual(final["corroborations"], [0])
        self.assertEqual(final["support_count"], 1)
        self.assertEqual(len(final["direct_statements"]), 2)
        self.assertEqual([x["speaker"] for x in final["direct_statements"]], [0, 4])
        self.assertEqual(final["speakers"][0]["trust"], 65)
        self.assertEqual(final["speakers"][0]["patience"], 2)
        self.assertEqual(final["influence"], 19)
        self.assertEqual(final["position"], 2)
        self.assertEqual(final["attention_spent"], 4)
        self.assertEqual(final["unmodeled_speakers"], 12)
        self.assertTrue(all(x["source"] == "original_first_hand_speaker_statement"
                            for x in final["direct_statements"]))
        ended = run_advanced_session("dialogue",
                                   actions=[*CONSENSUS, "retire"], seed=2, scene=scene)
        self.assertTrue(ended["state"]["finished"])
        self.assertTrue(ended["state"]["retired"])
        self.assertTrue(ended["terminal"])
        self.assertTrue(verify_advanced_session(ended))

    def test_no_teleport_remote_speech_or_forged_omniscient_corroboration(self):
        for actions in (
            ["speak:4"], ["support:0"], ["challenge:0"],
            ["travel:2"], ["compare:0"], ["claim"], ["retire"],
            ["speak:0", "speak:0"], ["speak:0", "compare:0"],
            ["speak:0", "travel:1", "speak:4", "travel:2", "compare:1"],
        ):
            with self.subTest(actions=actions):
                with self.assertRaises(AdvancedRuntimeError):
                    run_advanced_session("dialogue", actions=actions)

    def test_choices_cost_real_influence_and_have_distinct_social_consequences(self):
        supported = run_advanced_session("dialogue",
                                         actions=["speak:0", "support:0"])["state"]
        challenged = run_advanced_session("dialogue",
                                          actions=["speak:0", "challenge:0"])["state"]
        self.assertGreater(supported["reputation"], challenged["reputation"])
        self.assertGreater(supported["speakers"][0]["trust"],
                           challenged["speakers"][0]["trust"])
        self.assertEqual(supported["influence"], 19)
        self.assertEqual(challenged["influence"], 20)
        self.assertEqual(supported["choices"][0]["branch"], "support")
        self.assertEqual(challenged["choices"][0]["branch"], "challenge")
        toggled = {"choice_consequences": False}
        for action in ("support:0", "challenge:0"):
            with self.assertRaises(AdvancedRuntimeError):
                run_advanced_session("dialogue", toggled, ["speak:0", action])
        passive = run_advanced_session("dialogue", toggled, ["speak:0", "inspect"])
        self.assertEqual(passive["state"]["support_count"], 0)

    def test_finite_dialogue_budgets_and_non_solvable_worlds_remain_playable(self):
        sparse = {"speakers": 500, "active_speakers_budget": 3,
                  "lines_per_scene": 1}
        scene = make_advanced_scene("dialogue", sparse, seed=9)
        output = run_advanced_session("dialogue", sparse,
                                      ["speak:0", "inspect"], seed=9, scene=scene)
        self.assertEqual(output["state"]["active_speakers"], 3)
        self.assertEqual(output["state"]["unmodeled_speakers"], 497)
        self.assertFalse(output["state"]["checkpoint"])
        self.assertEqual(output["state"]["conversations"], 1)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("dialogue", sparse,
                                 ["speak:0", "travel:1", "speak:1"])
        self.assertTrue(verify_advanced_session(output, sparse))

    def test_memory_decay_is_finite_without_erasing_first_hand_evidence(self):
        limits = {"memory_turns": 2}
        output = run_advanced_session("dialogue", limits,
                                      ["speak:0", "wait", "wait", "wait"])
        self.assertTrue(verify_advanced_session(output, limits))
        self.assertEqual(output["state"]["speakers"][0]["memories"], [])
        self.assertEqual(len(output["state"]["direct_statements"]), 1)
        self.assertLessEqual(len(output["state"]["history"]), 2)
        zero = run_advanced_session("dialogue", {"memory_turns": 0},
                                    ["speak:0", "inspect"])
        self.assertEqual(zero["state"]["speakers"][0]["memories"], [])
        self.assertEqual(zero["state"]["history"], [])
        self.assertEqual(len(zero["state"]["direct_statements"]), 1)

    def test_source_identity_and_originality_are_verified_not_merely_recommended(self):
        cfg = make_editor_document("dialogue")["settings"]
        authored = make_advanced_scene("dialogue", seed=5)
        self.assertEqual(validate_advanced_scene(authored), authored)
        for mutate in (
            lambda x: x["speakers"][0].__setitem__("id", 7),
            lambda x: x["speakers"][1].__setitem__("name", "Original Voice 1"),
            lambda x: x["speakers"][0].__setitem__("testimony", 500),
            lambda x: x.__setitem__("provenance", "external_generated_asset"),
            lambda x: x.__setitem__("origin", 99),
            lambda x: x["speakers"][0].__setitem__("unexpected", True),
        ):
            forged = deepcopy(authored["layout"])
            mutate(forged)
            with self.subTest(mutate=mutate):
                with self.assertRaises(SceneError):
                    make_advanced_scene("dialogue", seed=5, layout=forged)
        self.assertEqual(len(normalize_layout(cfg, default_layout(cfg, 5))["speakers"]), 8)

    def test_forged_trust_testimony_terminal_reward_and_source_are_denied(self):
        receipt = run_advanced_session("dialogue", actions=CONSENSUS)
        for corrupt in (
            lambda x: x["state"]["speakers"][0].__setitem__("trust", 100),
            lambda x: x["state"].__setitem__("checkpoint", False),
            lambda x: x["state"]["direct_statements"][0].__setitem__("speaker", 7),
            lambda x: x["state"].__setitem__("influence", 100000),
            lambda x: x["actions"].append("retire"),
            lambda x: x.__setitem__("native_hardware_verified", True),
        ):
            forged = deepcopy(receipt)
            corrupt(forged)
            with self.subTest(corrupt=corrupt):
                with self.assertRaises(AdvancedRuntimeError):
                    verify_advanced_session(forged)

    def test_dialogue_and_npc_world_evidence_compose_without_false_runtime_claims(self):
        result = compile_system_assembly(
            "original_talking_world",
            [make_editor_document("dialogue", {"speakers": 8}),
             make_editor_document("npc_society", {"population": 64})],
            authorized=True,
        )
        self.assertTrue(result["advanced_evidence"])
        played = {x["editor"] for x in result["advanced_evidence"]}
        self.assertIn("dialogue", played)
        self.assertIn("npc_society", played)


if __name__ == "__main__":
    unittest.main()
