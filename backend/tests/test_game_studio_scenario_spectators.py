"""Authenticated spectator and scenario-draft surfaces must remain read-only."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import unittest

from core import game_studio_learning
from core.game_learning import GameLearningError
from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest
from skeleton.jeeves.game_studio_environment import (
    make_studio_source, studio_request_tree,
)


class _WorkerCredits:
    """Only the Mongo lease adapter is in memory; probes execute real code."""

    def __init__(self):
        self.rows = {}
        self.claims = []
        self.releases = []

    @staticmethod
    def matches(row, query):
        for key, expected in query.items():
            actual = row.get(key)
            if isinstance(expected, dict):
                for operator, value in expected.items():
                    if operator == "$in":
                        if actual not in value:
                            return False
                    elif operator == "$lt":
                        if actual is None or not actual < value:
                            return False
                    elif operator == "$gt":
                        if actual is None or not actual > value:
                            return False
                    else:
                        raise AssertionError(f"Unsupported lease operator: {operator}")
            elif actual != expected:
                return False
        return True

    @staticmethod
    def apply(row, update):
        row.update(deepcopy(update.get("$set", {})))
        for key in update.get("$unset", {}):
            row.pop(key, None)

    async def update_one(self, query, update, *, upsert=False):
        row = next((row for row in self.rows.values() if self.matches(row, query)), None)
        if row is None and upsert:
            row = {"_id": query["_id"], **deepcopy(update.get("$setOnInsert", {}))}
            self.rows[row["_id"]] = row
        if row is not None:
            self.apply(row, update)
        return SimpleNamespace(matched_count=int(row is not None))

    async def find_one_and_update(self, query, update, *, return_document):
        row = next((row for row in self.rows.values() if self.matches(row, query)), None)
        if row is None:
            return None
        self.apply(row, update)
        self.claims.append(deepcopy(row))
        return deepcopy(row)

    async def find_one(self, query, projection=None):
        return next((deepcopy(row) for row in self.rows.values() if self.matches(row, query)), None)

    async def update_many(self, query, update):
        matched = [row for row in self.rows.values() if self.matches(row, query)]
        for row in matched:
            self.releases.append(deepcopy(row))
            self.apply(row, update)
        return SimpleNamespace(matched_count=len(matched))


class TestStudioScenarioSpectators(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.scope={"tenant_id":"tenant-fixture", "owner_id":"owner-fixture"}
        self.workers = _WorkerCredits()
        for replacement in (
            patch.object(game_studio_learning.workspace, "workers", self.workers),
            patch("core.game_play.resource_profiles", return_value={"profiles": [{
                "profile_id": "cpu", "available": True,
                "training_credit_ids": ["game-learning-actor:fixture"],
            }]}),
        ):
            replacement.start()
            self.addCleanup(replacement.stop)
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

    def assert_capacity_released(self, count):
        self.assertEqual(len(self.workers.claims), count)
        self.assertEqual(len(self.workers.releases), count)
        self.assertEqual(
            [row["worker_token"] for row in self.workers.claims],
            [row["worker_token"] for row in self.workers.releases],
        )
        for claim in self.workers.claims:
            self.assertEqual(claim["tenant_id"], self.scope["tenant_id"])
            self.assertEqual(claim["owner_id"], self.scope["owner_id"])
            self.assertEqual(claim["resource_class"], "studio_probe")
        for row in self.workers.rows.values():
            self.assertNotIn("worker_token", row)
            self.assertLessEqual(row["lease_until"], datetime.now(timezone.utc))

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
        # Two independent angles share one resource-bounded local worker.
        self.assertEqual(report["workers_used"],1)
        self.assertTrue(all(lane["steps"]>0 for lane in report["lanes"]))
        self.assertEqual(self.row["cursor"],7)
        self.assert_capacity_released(1)

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
        self.assert_capacity_released(1)
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
        self.assert_capacity_released(2)
        with self.assertRaises(GameLearningError):
            await game_studio_learning.multifactor_verified_experiments(
                self.scope,"campaign-fixture",count=17,
            )

    async def test_occupied_shared_credit_refuses_diagnostic(self):
        occupied = {
            "_id": "game-learning-actor:fixture",
            "worker_token": "training-owner",
            "resource_class": "training",
            "lease_until": datetime.now(timezone.utc) + timedelta(seconds=30),
        }
        self.workers.rows[occupied["_id"]] = deepcopy(occupied)
        with patch.object(game_studio_learning, "_read", new_callable=AsyncMock) as reader:
            reader.return_value = self.row
            with self.assertRaises(GameLearningError) as failure:
                await game_studio_learning.scenario_mirror_views(
                    self.scope, "campaign-fixture", lanes=1, steps=1,
                )
        self.assertEqual(failure.exception.code, "studio_compute_busy")
        self.assertEqual(reader.await_count, 1)
        self.assertEqual(self.workers.rows[occupied["_id"]], occupied)
        self.assertEqual(self.workers.claims, [])
        self.assertEqual(self.workers.releases, [])

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
