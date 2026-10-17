"""Actually execute generated HTML5 JavaScript, guard exact source identity.

Node VM probes the genuine runtime script (not a copied game simulator). The
DOM/Canvas is an instrumented fixture, not a graphical browser or hardware.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from skeleton.ai.game_builder.studio_asset_pipeline import ArtDirection
from skeleton.ai.game_builder.studio_campaign import CampaignOrder, run_campaign
from skeleton.ai.game_builder.studio_campaign_assurance import (
    StudioAssuranceError, inspect_production_assurance, qualify_campaign_browser,
)
from skeleton.ai.game_builder.studio_runtime_qualification import (
    StudioRuntimeQualificationError, qualify_browser_gameplay,
)


class RuntimeReplayQualificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        document = self.root / "authorship.txt"
        document.write_text("All original characters, source and art are owned by studio")
        self.order = CampaignOrder(
            project_id="original-browser-runtime",
            title="Jeeves Executed Game",
            seed=733, targets=("nintendo_game_boy",),
            source_basis="bandai_wonderswan", rights_document=str(document),
            creative_identity=("original-art", "original-game"),
            width=11, height=11, levels=1, collectibles=1, hazards=1,
            health=4, theme="ocean",
            art=ArtDirection(seed=733, animation_frames=3,
                             music_density=0, parallax_layers=0),
        )
        self.campaign = self.root / "campaign"
        state = run_campaign(self.order, self.campaign, authorized=True)
        self.assertEqual(state["targets_with_verified_source"], 1)
        self.engine = self.campaign / "targets/nintendo_game_boy/engines"

    def test_no_node_is_not_faked_as_runtime_pass(self):
        with patch("skeleton.ai.game_builder.studio_runtime_qualification.shutil.which",
                   return_value=None):
            result = qualify_browser_gameplay(self.engine, authorized=True, execute=True)
        receipt = result.as_receipt()
        self.assertFalse(receipt["node_available"])
        self.assertFalse(receipt["javascript_executed"])
        self.assertFalse(receipt["winning_replay_verified"])
        self.assertEqual(receipt["failure"], "node_not_installed")
        self.assertFalse(receipt["graphical_browser_pixels_verified"])

    def test_preflight_does_not_execute_node(self):
        with patch("skeleton.ai.game_builder.studio_runtime_qualification.shutil.which",
                   return_value="/path/to/node"), patch(
                "skeleton.ai.game_builder.studio_runtime_qualification.subprocess.run"
            ) as runtime:
            result = qualify_browser_gameplay(self.engine, authorized=True, execute=False)
        runtime.assert_not_called()
        self.assertFalse(result.javascript_executed)
        self.assertEqual(result.failure, "javascript_execution_not_authorized")
        with self.assertRaises(PermissionError):
            qualify_browser_gameplay(self.engine, authorized=False, execute=True)
        with self.assertRaises(StudioRuntimeQualificationError):
            qualify_browser_gameplay(self.engine, authorized=True, execute=True,
                                     timeout_seconds=0)

    def test_real_node_replays_actual_generated_javascript_and_draws_sprite_frames(self):
        if shutil.which("node") is None:
            self.skipTest("Node JavaScript runtime not installed on this test machine")
        result = qualify_browser_gameplay(
            self.engine, authorized=True, execute=True, timeout_seconds=45,
        )
        self.assertTrue(result.node_available)
        self.assertTrue(result.javascript_executed)
        self.assertTrue(result.winning_replay_verified, result.failure)
        self.assertGreater(result.canvas_draw_calls, 64)
        self.assertTrue(result.sprite_draws_exercised)
        self.assertTrue(result.animation_tick_exercised)
        self.assertFalse(result.as_receipt()["graphical_browser_pixels_verified"])
        qualified = qualify_campaign_browser(
            self.order, self.campaign, "nintendo_game_boy",
            authorized=True, execute=True, timeout_seconds=45,
        )
        self.assertTrue(qualified["javascript_gameplay_executed"])
        inspected = inspect_production_assurance(self.order, self.campaign)
        self.assertEqual(inspected["browser_javascript_playthroughs_verified"], 1)
        self.assertEqual(inspected["checked_gates"], 8)
        self.assertEqual(
            inspected["targets"][0]["gates"]["browser_javascript_playthrough_executed"]["status"],
            "javascript_gameplay_executed",
        )
        repeated = qualify_campaign_browser(
            self.order, self.campaign, "nintendo_game_boy",
            authorized=True, execute=True,
        )
        self.assertTrue(repeated["already_qualified"])
        self.assertFalse(inspected["all_targets_release_ready"])

    def test_source_edit_rejects_stale_javascript_playthrough_claim(self):
        if shutil.which("node") is None:
            self.skipTest("Node JavaScript runtime not installed on this test machine")
        first = qualify_campaign_browser(
            self.order, self.campaign, "nintendo_game_boy",
            authorized=True, execute=True,
        )
        self.assertTrue(first["javascript_gameplay_executed"])
        target = self.engine / "index.html"
        target.write_bytes(target.read_bytes() + b"\n<!-- original editor altered output -->")
        with self.assertRaises((StudioAssuranceError, ValueError)):
            inspect_production_assurance(self.order, self.campaign)
        with self.assertRaises((StudioAssuranceError, ValueError)):
            qualify_campaign_browser(
                self.order, self.campaign, "nintendo_game_boy",
                authorized=True, execute=True,
            )

    def test_wrong_project_or_replay_prevents_unqualified_execution(self):
        proof = self.engine / "proof/verified_solution.json"
        original = json.loads(proof.read_text())
        original["world_digest"] = sha256(b"foreign project").hexdigest()
        proof.write_text(json.dumps(original))
        with self.assertRaises(StudioRuntimeQualificationError):
            qualify_browser_gameplay(self.engine, authorized=True, execute=True)
        with self.assertRaises((StudioAssuranceError, ValueError)):
            inspect_production_assurance(self.order, self.campaign)


if __name__ == "__main__":
    unittest.main()
