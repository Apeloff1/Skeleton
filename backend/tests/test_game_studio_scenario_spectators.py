"""Authenticated spectator and scenario-draft surfaces must remain read-only."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch
import unittest

from core import game_studio_learning
from core.game_learning import GameLearningError
from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest
from skeleton.jeeves.game_studio_environment import (
    make_studio_source, studio_request_tree,
)


class TestStudioScenarioSpectators(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.scope={"tenant_id":"tenant-fixture", "owner_id":"owner-fixture"}
        request=GameEnvironmentRequest(
            "studio:economy",kind="studio",
            tree=studio_request_tree(make_studio_source(
                "economy",{"market_nodes":2,"goods":10},
            )),max_steps=12,
        )
        self.request=request
        self.row={
            "campaign_id":"campaign-fixture",
            "environment_request":request.as_dict(),
            "snapshot": {"champion_request":request.as_dict()},
            "config":{"seed":3},"cursor":7,"status":"running",
        }

    async def test_owner_bound_simulations_are_actual_and_without_writes(self):
        with patch.object(game_studio_learning,"_read",new_callable=AsyncMock) as reader:
            reader.return_value=self.row
            report=await game_studio_learning.scenario_mirror_views(
                self.scope,"campaign-fixture",lanes=2,steps=3,sample=1,
            )
            # The second read is a post-computation authorization recheck.
            self.assertEqual(reader.await_count, 2)
            reader.assert_awaited_with(self.scope,"campaign-fixture")
        self.assertEqual(report["campaign_id"],"campaign-fixture")
        self.assertEqual(report["campaign_cursor"],7)
        self.assertTrue(report["spectator_only"])
        self.assertFalse(report["frames_show_training_episodes"])
        self.assertEqual(len(report["lanes"]),2)
        self.assertEqual(report["workers_used"],2)
        self.assertTrue(all(lane["steps"]>0 for lane in report["lanes"]))
        self.assertEqual(self.row["cursor"],7)

    async def test_shadow_scrutiny_is_scoped_readonly_and_never_fabricates_saturation(self):
        with patch.object(game_studio_learning,"_read",new_callable=AsyncMock) as reader:
            reader.return_value=self.row
            outcome=await game_studio_learning.scenario_shadow_audit(
                self.scope,"campaign-fixture",angle="temporal",
                steps=1,max_cycles=10,replay_budget=300,
            )
            # The second read is a post-computation authorization recheck.
            self.assertEqual(reader.await_count, 2)
            reader.assert_awaited_with(self.scope,"campaign-fixture")
        self.assertEqual(outcome["campaign_id"],"campaign-fixture")
        self.assertEqual(outcome["parent_sim_count"],1)
        self.assertTrue(outcome["spectator_only"])
        self.assertFalse(outcome["training_weight_changes"])
        sim=outcome["simulations"][0]
        self.assertEqual(sim["angle"],"temporal")
        self.assertLessEqual(sim["cycles_executed"],10)
        self.assertFalse(sim["universal_learning_exhaustion_proven"])
        self.assertEqual(self.row["cursor"],7)
        with self.assertRaises(GameLearningError):
            await game_studio_learning.scenario_shadow_audit(
                self.scope,"campaign-fixture",angle="foreign_python",
            )

    async def test_source_bound_multifactor_capability_and_two_real_experiments(self):
        with patch.object(game_studio_learning,"_read",new_callable=AsyncMock) as reader:
            reader.return_value=self.row
            catalog=await game_studio_learning.multifactor_control_catalog(
                self.scope,"campaign-fixture",
            )
            design=await game_studio_learning.multifactor_plan_preview(
                self.scope,"campaign-fixture",axis_offset=0,count=2,order=3,
            )
            experiment=await game_studio_learning.multifactor_verified_experiments(
                self.scope,"campaign-fixture",axis_offset=0,count=2,steps=1,
            )
            # Catalog reads once; both compute probes recheck campaign access.
            self.assertEqual(reader.await_count,5)
        self.assertEqual(catalog["editor"],"economy")
        self.assertGreater(catalog["total_executable_axes"],1)
        self.assertTrue(design["scenarios"])
        self.assertTrue(experiment["spectator_only"])
        self.assertEqual(experiment["actual_q_weight_updates"],0)
        self.assertEqual(experiment["scenarios_executed"],2)
        self.assertFalse(experiment["production_neural_weights_modified"])
        self.assertEqual(self.row["cursor"],7)
        with self.assertRaises(GameLearningError):
            await game_studio_learning.multifactor_verified_experiments(
                self.scope,"campaign-fixture",count=17,
            )

    async def test_malformed_parallel_and_campaign_source_rejected(self):
        with self.assertRaises(GameLearningError):
            await game_studio_learning.scenario_mirror_views(
                self.scope,"campaign-fixture",lanes=999,
            )
        denied={**self.row,"environment_request":{
            **self.request.as_dict(),"kind":"builtin",
        }}
        with patch.object(game_studio_learning,"_read",new_callable=AsyncMock) as read:
            read.return_value=denied
            with self.assertRaises((GameLearningError,ValueError)):
                await game_studio_learning.scenario_mirror_views(
                    self.scope,"campaign-fixture",lanes=2,
                )


    async def test_canonical_authority_cannot_be_laundered_by_a_valid_snapshot(self):
        # A malicious or stale campaign row must not inherit permission from
        # an independently well-formed champion snapshot with matching target.
        denied={**self.row,"environment_request":{
            **self.request.as_dict(),"kind":"builtin",
        }}
        with patch.object(game_studio_learning,"_read",new_callable=AsyncMock) as read:
            read.return_value=denied
            with self.assertRaises((GameLearningError,ValueError)):
                await game_studio_learning.scenario_mirror_views(
                    self.scope,"campaign-fixture",lanes=1,steps=1,
                )
            with self.assertRaises((GameLearningError,ValueError)):
                await game_studio_learning.scenario_shadow_audit(
                    self.scope,"campaign-fixture",steps=1,
                )
            with self.assertRaises((GameLearningError,ValueError)):
                await game_studio_learning.multifactor_control_catalog(
                    self.scope,"campaign-fixture",
                )
            self.assertEqual(read.await_count,3)


if __name__ == "__main__":
    unittest.main()
