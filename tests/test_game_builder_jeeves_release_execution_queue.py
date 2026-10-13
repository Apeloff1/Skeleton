"""True release evidence blocker queue: source contracts never make app green."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.jeeves_appwide_fabric import (
    JeevesAppwideError, JeevesAppwideRuntime)
from skeleton.ai.game_builder.jeeves_release_execution_queue import (
    JeevesReleaseExecutionQueue)
from tests.test_game_builder_jeeves_enterprise_journey_frontier import (
    EnterpriseJourneyFrontierTests)


class ReleaseExecutionQueueTests(unittest.TestCase):
    def setUp(self):
        self.fixture=EnterpriseJourneyFrontierTests(
            "test_whole_enterprise_journey_denominator_is_not_test_linkage")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.scope=self.fixture.scope
        self.docs=self.fixture.docs
        self.inv=self.fixture.inv
        for row in self.scope["families"]:
            row["acceptance_target"]="Independently verified real user and runtime behavior"
        self.docs["skeleton/app/manifest.json"]["services"]=[
            {"name":name} for name in (
                "frontend","backend","skeleton","mongo","chroma")]
        self.fixture.refresh()
        self.queue=JeevesReleaseExecutionQueue(self.inv)

    def test_leaf_requirements_are_complete_and_not_signed(self):
        status=self.queue.overview()
        self.assertEqual(status["leaf_evidence_denominator"],310)
        self.assertEqual(status["category_leaf_breakdown"],{
            "ai_product":9,
            "enterprise_journey_axis":84,
            "enterprise_workstream":16,
            "family_acceptance_stage":168,
            "release_gate":26,
            "runtime_service":5,
            "volume_enterprise_qualification":2,
        })
        self.assertEqual(status["independent_leaf_proofs_verified_by_this_reader"],0)
        self.assertEqual(status["leaf_proofs_unverified_by_this_reader"],310)
        self.assertEqual(status["product_family_denominator"],42)
        self.assertIsNone(status["full_app_completion_percent"])
        self.assertFalse(status["release_proven_from_this_source_scan"])
        self.assertEqual(status,self.queue.overview())

    def test_bounded_release_queue_is_deterministic_and_keyed(self):
        overview=self.queue.overview()
        tasks=[]
        offset=0
        while True:
            page=self.queue.page(offset=offset,limit=39,
                expected_queue_digest=overview["digest"])
            tasks.extend(page["tasks"])
            offset=page["next_offset"]
            if offset is None:
                break
        self.assertEqual(len(tasks),310)
        self.assertEqual(len(set(task["id"] for task in tasks)),310)
        self.assertEqual(tasks[0]["category"],"release_gate")
        self.assertEqual(tasks[-1]["category"],
                         "volume_enterprise_qualification")
        self.assertTrue(all(row["evidence_status"]=="unverified" for row in tasks))
        self.assertTrue(all(row["automatic_execution_authorized"] is False
                            for row in tasks))
        self.assertTrue(all(row["release_qualification_credited"] is False
                            for row in tasks))

    def test_journey_axes_and_family_test_stages_do_not_collapse(self):
        journeys=self.queue.page(category="enterprise_journey_axis",limit=50)
        families=self.queue.page(category="family_acceptance_stage",limit=50)
        self.assertEqual(journeys["total_matches"],84)
        self.assertEqual(families["total_matches"],168)
        self.assertEqual(journeys["next_offset"],50)
        self.assertEqual(families["next_offset"],50)
        self.assertTrue(all(row["category"]=="enterprise_journey_axis"
                            for row in journeys["tasks"]))
        self.assertTrue(all(row["category"]=="family_acceptance_stage"
                            for row in families["tasks"]))

    def test_source_changes_invalidate_accepted_queue_identity(self):
        previous=self.queue.overview()
        self.docs["machine/ai_capabilities.json"]["capabilities"][0][
            "implementation_state"]="complete"
        self.fixture.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.queue.page(expected_queue_digest=previous["digest"])
        actual=self.queue.overview()
        self.assertNotEqual(previous["digest"],actual["digest"])
        self.assertEqual(actual["independent_leaf_proofs_verified_by_this_reader"],0)
        self.assertIsNone(actual["full_app_completion_percent"])

    def test_fake_execution_count_cannot_be_passed_as_user_input(self):
        with self.assertRaises(TypeError):
            self.queue.overview(complete=310)
        with self.assertRaises(TypeError):
            self.queue.page(release_verified=True)

    def test_finite_source_plan_volume_key_identity(self):
        before=deepcopy(self.docs["machine/ai_master_plan.json"]["volumes"])
        self.docs["machine/ai_master_plan.json"]["volumes"][1]["id"]=0
        self.fixture.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.queue.overview()
        self.docs["machine/ai_master_plan.json"]["volumes"]=before
        self.fixture.refresh()
        self.assertEqual(self.queue.overview()["declared_volume_count"],2)

    def test_unsafe_boolean_offsets_and_unknown_category_denied(self):
        for params in (
            {"limit":True},{"offset":False},{"offset":-1},
            {"limit":0},{"limit":51},{"category":"phantom"},
            {"category":True},
        ):
            with self.subTest(params=params),self.assertRaises(JeevesAppwideError):
                self.queue.page(**params)

    def test_jeeves_operation_is_read_only_and_paginates_earliest_gates(self):
        operator=JeevesAppwideRuntime(self.inv)
        report=operator.invoke("ai.product.release.queue",{})
        self.assertTrue(report["read_only_or_review_only"])
        self.assertEqual(report["result"]["leaf_evidence_denominator"],310)
        first=operator.invoke("ai.product.release.queue.page",{
            "limit":2,
            "expected_queue_digest":report["result"]["digest"]})["result"]
        self.assertEqual(len(first["tasks"]),2)
        self.assertTrue(first["release_signoff_not_claimed"])
        self.assertEqual(first["tasks"][0]["category"],"release_gate")


if __name__=="__main__":
    unittest.main()
