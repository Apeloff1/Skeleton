"""Living-world continuation recreates authoritative NPC and ecosystem histories."""
from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_gameplay_save import (
    SavegameError, export_advanced_savegame, import_advanced_savegame,
    continue_advanced_savegame,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    run_advanced_session,verify_advanced_session,
)


class LivingWorldSavegameTests(unittest.TestCase):
    def test_society_continuation_replays_witnesses_and_lod_without_minting_memory(self):
        settings={"simulation_lod":"background","coarse_period":16}
        initial=run_advanced_session(
            "npc_society",settings,["observe","focus:1"],
        )
        saved=export_advanced_savegame(initial,settings)
        recovered=import_advanced_savegame(saved)
        self.assertEqual(recovered["session"]["digest"],initial["digest"])
        extended=continue_advanced_savegame(saved,["observe","east","talk"])
        resumed=import_advanced_savegame(extended)["session"]
        self.assertTrue(verify_advanced_session(resumed,settings))
        self.assertEqual(resumed["state"]["evidence"],
                         ["observed_resident_0","observed_resident_1"])
        self.assertEqual(resumed["actions"],
                         ["observe","focus:1","observe","east","talk"])

    def test_ecology_continuation_earns_real_nonterminal_milestone(self):
        initial=run_advanced_session("ecosystem",actions=["survey","plant"])
        saved=export_advanced_savegame(initial)
        continued=continue_advanced_savegame(
            saved,["east","north","survey","checkpoint"]
        )
        session=import_advanced_savegame(continued)["session"]
        self.assertTrue(session["state"]["conservation_checkpoint"])
        self.assertFalse(session["state"]["finished"])
        self.assertTrue(verify_advanced_session(session))

    def test_savegame_forged_social_evidence_or_biodiversity_fails_closed(self):
        for editor,actions in (
            ("npc_society",["talk"]),
            ("ecosystem",["survey","plant"]),
        ):
            session=run_advanced_session(editor,actions=actions)
            saved=export_advanced_savegame(session)
            forged=deepcopy(saved)
            forged["actions"].append("checkpoint")
            with self.assertRaises(SavegameError):
                import_advanced_savegame(forged)
            forged=deepcopy(saved)
            forged["session_digest"]="0"*64
            with self.assertRaises(SavegameError):
                import_advanced_savegame(forged)

    def test_background_workload_is_identical_across_save_continuation(self):
        settings={"species":500,"predators":100,"cohort_period":2}
        initial=run_advanced_session("ecosystem",settings,["wait"])
        saved=export_advanced_savegame(initial,settings)
        continued=import_advanced_savegame(
            continue_advanced_savegame(saved,["wait","wait"])
        )["session"]
        fresh=run_advanced_session("ecosystem",settings,["wait"]*3)
        self.assertEqual(continued["digest"],fresh["digest"])
        self.assertEqual(continued["state"]["background_batches"],
                         fresh["state"]["background_batches"])
        self.assertTrue(verify_advanced_session(continued,settings))


if __name__=="__main__":
    unittest.main()
