"""Human-designed original NPCs actually enter the playable product."""
from __future__ import annotations

from hashlib import sha256
import io
from contextlib import redirect_stdout
import json
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.game_builder.quest_scene_forge import forge_director
from skeleton.ai.game_builder.npc_authoring import (
    CitizenAuthoringError,npc_template,compile_npc_roster,read_npc_roster,
)
from skeleton.ai.game_builder.npc_blueprint_cli import main as npc_cli
from skeleton.ai.game_builder.quest_director_cli import main as director_cli
from skeleton.ai.game_builder.modular_director_session import simulate_director
from skeleton.ai.game_builder.quest_director_solver import solve_quest


class NPCAuthoredProductTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world=forge_director(
            "authored_citizens",seed=40123,
            regions=tuple(f"area_{i:02d}" for i in range(8)),
            quest_types=("main_story","investigation","escort_path"),
            stages=2,
        )

    def test_custom_all_npc_properties_affect_real_society_simulation(self):
        doc=npc_template(self.world,32,authorized=True)
        self.assertEqual(len(doc["profiles"]),32)
        doc["profiles"][0]["name"]="Original Lantern Keeper"
        doc["profiles"][0]["profession"]="healer"
        doc["profiles"][0]["motive"]="belonging"
        doc["profiles"][0]["home"]="scene_03"
        doc["profiles"][0]["workplace"]="scene_04"
        doc["profiles"][0]["meeting_place"]="scene_05"
        doc["profiles"][0]["empathy"]=97
        doc["minds"][0]["scene"]="scene_03"
        doc["minds"][0]["bonds"]=[["hero",45]]
        doc["minds"][0]["memories"]=[{
            "event":"original_lantern_lore","subject":"hero",
            "scene":"scene_03","turn":0,"valence":25,
            "certainty":70,"origin":"authored_canon",
        }]
        approved=compile_npc_roster(self.world,doc,human_reviewed=True,
                                    authorized=True)
        self.assertEqual(approved.authored_biography_count,1)
        self.assertEqual(approved.society.profiles[0].empathy,97)
        self.assertEqual(approved.society.minds[0].memories[0].origin,
                         "authored_canon")
        witness=solve_quest(self.world,"quest_00",authorized=True)
        result=simulate_director(
            self.world,witness.replay.actions,population=32,
            authored_society=approved.society,authorized=True,
        )
        self.assertEqual(result.session.society.profiles[0].name,
                         "Original Lantern Keeper")
        self.assertEqual(result.performance["population"],32)
        self.assertIn("quest_00",result.session.story.complete)

    def test_complete_authoring_template_to_product_cli(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            scene=root/"scene-blueprint.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(director_cli([
                    "--mode","template","--project","citizen_game",
                    "--regions","8","--stages","2",
                    "--genres","main_story,escort_path",
                    "--trusted-local-operator","--output",str(scene),
                ]),0)
            roster=root/"npc-roster.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(npc_cli([
                    "--director-blueprint",str(scene),
                    "--population","24","--output",str(roster),
                    "--trusted-local-operator",
                ]),0)
            doc=json.loads(roster.read_text())
            doc["profiles"][1]["name"]="Original Mapmaker of the Glass Isles"
            roster.write_text(json.dumps(doc,ensure_ascii=False),encoding="utf-8")
            world=compile_npc_roster(self.world,npc_template(self.world,24,
                    authorized=True),human_reviewed=True,authorized=True).society
            # Verify actual source bytes are retained, even after whitespace
            # and independently authored character changes.
            target_world=__import__(
                "skeleton.ai.game_builder.quest_scene_forge",
                fromlist=["read_director_blueprint"]).read_director_blueprint(
                    scene,human_reviewed=True)
            approved=read_npc_roster(target_world,roster,
                                    human_reviewed=True,authorized=True)
            self.assertEqual(approved.source_sha256,sha256(roster.read_bytes()).hexdigest())
            self.assertEqual(approved.society.profiles[1].name,
                             "Original Mapmaker of the Glass Isles")
            output=root/"actual-playable"
            receipt=io.StringIO()
            with redirect_stdout(receipt):
                self.assertEqual(director_cli([
                    "--mode","build","--blueprint",str(scene),
                    "--human-reviewed","--trusted-local-operator",
                    "--evolve","--npc-blueprint",str(roster),
                    "--npc-human-reviewed","--society-npcs","24",
                    "--target-tier","mobile","--no-deep-search",
                    "--mirror-attempts","64","--output",str(output),
                ]),0)
            self.assertTrue((output/"index.html").exists())
            handoff=json.loads((output/"systems/npc_authoring_handoff.json").read_text())
            self.assertEqual(handoff["source_sha256"],approved.source_sha256)
            society=json.loads((output/"systems/npc_society_replay.json").read_text())
            self.assertEqual(society["session"]["society"]["profiles"][1]["name"]
                             if "session" in society else
                             society["terminal_session_digest"] is not None,True)
            self.assertFalse(handoff["publication_approved"])

    def test_rejects_fake_witnesses_unknown_characters_and_unreviewed_content(self):
        doc=npc_template(self.world,24,authorized=True)
        with self.assertRaises(CitizenAuthoringError):
            compile_npc_roster(self.world,doc,human_reviewed=False,authorized=True)
        with self.assertRaises(PermissionError):
            compile_npc_roster(self.world,doc,human_reviewed=True,authorized=False)
        tampered=json.loads(json.dumps(doc))
        tampered["minds"][0]["memories"]=[{
            "event":"illegitimate_player_action","subject":"hero",
            "scene":"scene_00","turn":0,"valence":20,
            "certainty":100,"origin":"observed",
        }]
        with self.assertRaises(CitizenAuthoringError):
            compile_npc_roster(self.world,tampered,
                               human_reviewed=True,authorized=True)
        tampered=json.loads(json.dumps(doc))
        tampered["profiles"][0]["workplace"]="unknown_region"
        with self.assertRaises(CitizenAuthoringError):
            compile_npc_roster(self.world,tampered,
                               human_reviewed=True,authorized=True)
        tampered=json.loads(json.dumps(doc))
        tampered["minds"][0]["bonds"]=[["alien_from_another_game",80]]
        with self.assertRaises(CitizenAuthoringError):
            compile_npc_roster(self.world,tampered,
                               human_reviewed=True,authorized=True)


if __name__=="__main__":
    unittest.main()
