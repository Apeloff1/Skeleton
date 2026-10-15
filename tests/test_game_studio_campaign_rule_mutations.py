"""Existing Jeeves studio campaigns must vary real, replayable studio rules."""
from __future__ import annotations

import json
import unittest

from skeleton.ai.game_builder.advanced_gameplay_runtime import verify_advanced_session
from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest
from skeleton.jeeves.game_studio_environment import (
    make_studio_source, studio_request_tree,
)
from skeleton.jeeves.game_studio_learning import StudioLearningCampaign


class StudioCampaignRuleMutationTests(unittest.TestCase):
    def _request(self, engine="economy"):
        return GameEnvironmentRequest(
            "studio:" + engine, kind="studio", max_steps=6,
            tree=studio_request_tree(make_studio_source(engine)),
        )

    def test_catalog_exposes_real_rules_not_unbounded_python(self):
        campaign=StudioLearningCampaign.__new__(StudioLearningCampaign)
        campaign.champion=self._request()
        arms=campaign.proposal_catalog()
        self.assertEqual(arms[0]["id"],"policy.continue")
        self.assertIn("studio.trade_tax",{row["id"] for row in arms})
        self.assertIn("studio.market_nodes",{row["id"] for row in arms})
        self.assertNotIn("studio.script",{row["id"] for row in arms})
        profile=self._request("platform_profile")
        arms=campaign.proposal_catalog(profile)
        self.assertNotIn("studio.homebrew_only",{row["id"] for row in arms})

    def test_campaign_candidate_mutates_source_and_runs_real_game(self):
        campaign=StudioLearningCampaign.__new__(StudioLearningCampaign)
        campaign.champion=self._request()
        catalog=campaign.proposal_catalog()
        arm=next(row for row in catalog if row["id"]=="studio.price_elasticity")
        campaign._select_proposal=lambda index:(arm,{"algorithm":"recorded-bandit-fixture"})
        campaign._seed=lambda index,purpose:42
        campaign._decision=lambda *args,**kwargs:(None,None)
        campaign._proposal_facts=lambda prior:{}
        candidate,facts=campaign._mutate(3)
        self.assertTrue(facts["supported"])
        self.assertEqual(facts["strategy"],
                         "bandit_selected_source_verified_game_rule")
        self.assertNotEqual(candidate.digest,campaign.champion.digest)
        self.assertEqual(candidate.kind,"studio")
        self.assertEqual(candidate.target_id,"studio:economy")
        old=json.loads(campaign.champion.tree["game/studio/session.json"])
        new=json.loads(candidate.tree["game/studio/session.json"])
        self.assertNotEqual(old["settings"]["price_elasticity"],
                            new["settings"]["price_elasticity"])
        self.assertEqual(old["actions"],new["actions"])
        self.assertTrue(facts["changes"][0]["source_rule_validated"])
        env=candidate.build()
        obs=env.reset(11)
        self.assertIn("score",obs)
        move=env.step("inspect")
        self.assertTrue(move.info["evidence"]["accepted"])
        self.assertEqual(env.snapshot()["actions"],["inspect"])
        env.close()

    def test_rejected_or_locked_rules_cannot_change_champion(self):
        campaign=StudioLearningCampaign.__new__(StudioLearningCampaign)
        campaign.champion=self._request("platform_profile")
        arms=campaign.proposal_catalog()
        self.assertNotIn("studio.homebrew_only",{a["id"] for a in arms})


if __name__ == "__main__":
    unittest.main()
