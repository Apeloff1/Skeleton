"""Enterprise journey readiness never follows source files or fake signatures."""
from __future__ import annotations

from copy import deepcopy
import json
import unittest

from skeleton.ai.game_builder.jeeves_appwide_fabric import (
    JeevesAppwideError, JeevesAppwideRuntime)
from skeleton.ai.game_builder.jeeves_enterprise_journey_frontier import (
    JeevesEnterpriseJourneyFrontier, AXES, POLICIES)
from tests.test_game_builder_jeeves_completion_census import CompletionCensusTests


class EnterpriseJourneyFrontierTests(unittest.TestCase):
    def setUp(self):
        self.fixture=CompletionCensusTests(
            "test_sources_and_declared_maturity_never_certify_product")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.inv=self.fixture.inv
        self.docs=self.fixture.docs
        self.canonical=[
            "real operator authenticates -> durable source-backed answer",
            "retrieval response -> source citation -> verified provenance",
            "signed action -> single authorized effect -> stable audit",
            "artifact ingest -> scan -> use -> explicit physical deletion",
            "model outage -> safe authorized failover or degrade",
            "operation queue -> hard stop -> idempotent resume",
            "stream consumer disconnect -> exactly one reconstructed result",
            "tenant data export and delete -> cross-plane lifecycle",
            "rate saturation -> bounded fairness and preserved writes",
            "failed canary -> rollback with compatible persisted data",
            "physical backup restore -> exact state and recovered indexes",
            "JIT privileged action -> immutable log -> expiry and refusal",
        ]
        self.docs["machine/enterprise_system_architecture.json"][
            "required_journeys"]=list(self.canonical)
        self.docs["machine/enterprise_system_architecture.json"][
            "implementation_workstreams"]=[
            {"id":"ENT-%02d"%n} for n in range(1,17)]
        self.docs["machine/ai_capabilities.json"]["capabilities"]=[
            {"capability_id":"cap.%02d"%n} for n in range(1,10)]
        self.gates={"gates":[
            {"id":"GATE-%02d"%n,
             "required_for_terminal_p1_promotion":True}
            for n in range(1,27)]}
        self.scope={"families":[{"id":"F%02d"%i} for i in range(1,43)]}
        self.name="tests/test_journey_real_candidate.py"
        self.fixture.put(self.name,
            "import unittest\nclass RealJourney(unittest.TestCase):\n"
            "  def test_actual_subset(self): self.assertTrue(True)\n")
        self.contract={
            "schema":"skeleton.ai.enterprise_journey_acceptance.v1",
            "source_authority":"machine/enterprise_system_architecture.json",
            "scope_authority":"machine/app_completion_scope.json",
            "required_acceptance_axes":list(AXES),
            "policy":{key:True for key in POLICIES},
            "journeys":[{
                "id":"J%02d"%n,
                "canonical_journey":self.canonical[n-1],
                "family_ids":["F01","F%02d"%(n+1)],
                "acceptance_target":
                    "Actual user outcome with durable state, denial and recovery proof",
                "acceptance_axes":list(AXES),
                "source_test_candidates":[self.name],
                "acceptance_receipts":[],
                "release_qualified":False,
                "operator_review_required":True,
            } for n in range(1,13)],
        }
        self.refresh()
        self.frontier=JeevesEnterpriseJourneyFrontier(self.inv)

    def refresh(self):
        self.fixture.flush()
        self.fixture.put("machine/p1_required_gate_authority.json",
                         json.dumps(self.gates,sort_keys=True))
        self.fixture.put("machine/app_completion_scope.json",
                         json.dumps(self.scope,sort_keys=True))
        self.fixture.put("machine/app_release_journey_contract.json",
                         json.dumps(self.contract,sort_keys=True))
        self.inv.scan()

    def test_whole_enterprise_journey_denominator_is_not_test_linkage(self):
        report=self.frontier.overview()
        self.assertEqual(report["canonical_journey_count"],12)
        self.assertEqual(report["required_acceptance_axes_per_journey"],7)
        self.assertEqual(report["total_journey_acceptance_axes"],84)
        self.assertEqual(report["unknown_journey_acceptance_axes"],84)
        self.assertEqual(report["independently_verified_journey_axes_observed"],0)
        self.assertEqual(report["required_terminal_gates"],26)
        self.assertIsNone(report["real_exact_head_gate_successes_observed"])
        self.assertEqual(report["AI_capability_contract_total"],9)
        self.assertEqual(report["enterprise_workstreams"],16)
        self.assertEqual(report["unique_candidate_test_file_count"],1)
        self.assertEqual(report["unique_candidate_test_function_declarations"],1)
        self.assertEqual(report["journeys_release_qualified_observed"],0)
        self.assertFalse(report["actual_app_release_qualified"])
        self.assertIsNone(report["full_app_completion_percent"])
        self.assertEqual(self.frontier.overview(),report)

    def test_paged_exact_source_bound_journeys_are_all_unknown(self):
        overview=self.frontier.overview()
        cursor=0
        seen=[]
        while True:
            page=self.frontier.page(
                offset=cursor,limit=5,expected_report_digest=overview["digest"])
            for journey in page["journeys"]:
                seen.append(journey["id"])
                self.assertEqual(journey["independently_verified_axes"],0)
                self.assertEqual(journey["missing_acceptance_axes"],7)
                self.assertFalse(journey["journey_release_qualified"])
                self.assertFalse(journey["tests_actually_executed_by_this_reader"])
                self.assertEqual(set(journey["axis_status"].values()),{"unverified"})
                self.assertTrue(journey["candidate_test_sources"])
            cursor=page["next_offset"]
            if cursor is None:break
        self.assertEqual(seen,["J%02d"%n for n in range(1,13)])
        self.assertEqual(len(set(seen)),12)

    def test_source_change_invalidates_old_cursor_and_hash_receipt(self):
        first=self.frontier.overview()
        self.contract["journeys"][0]["acceptance_target"]=(
            "Real user journey with authoritative exact operator audited outcome")
        self.refresh()
        second=self.frontier.overview()
        self.assertNotEqual(first["contract_sha256"],second["contract_sha256"])
        self.assertNotEqual(first["digest"],second["digest"])
        with self.assertRaises(JeevesAppwideError):
            self.frontier.page(expected_report_digest=first["digest"])
        with self.assertRaises(JeevesAppwideError):
            self.frontier.overview(expected_contract_sha256=first["contract_sha256"])

    def test_duplicate_missing_or_reordered_canonical_journey_refused(self):
        base=deepcopy(self.contract["journeys"])
        for changes in (base[:11],base[1:]+base[:1],base[:1]+base[:1]+base[2:]):
            self.contract["journeys"]=deepcopy(changes)
            self.refresh()
            with self.assertRaises(JeevesAppwideError):
                self.frontier.overview()
        self.contract["journeys"]=base

    def test_master_authority_changes_fail_not_autoresign(self):
        self.docs["machine/enterprise_system_architecture.json"][
            "required_journeys"][0]="unreviewed or renamed release journey"
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.frontier.overview()

    def test_software_or_human_fabricated_acceptance_signoff_refused(self):
        for field,bad in (
            ("release_qualified",True),("acceptance_receipts",[{"verified":True}]),
            ("operator_review_required",False),
            ("acceptance_axes",list(AXES[:-1])),
        ):
            old=deepcopy(self.contract["journeys"][0][field])
            self.contract["journeys"][0][field]=bad
            self.refresh()
            with self.subTest(field=field),self.assertRaises(JeevesAppwideError):
                self.frontier.overview()
            self.contract["journeys"][0][field]=old

    def test_release_gate_optionalization_is_an_explicit_blocker(self):
        self.gates["gates"][0]["required_for_terminal_p1_promotion"]=False
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.frontier.overview()

    def test_test_file_cannot_be_replaced_with_no_tests(self):
        self.fixture.put(self.name,"def helper_only(): return 1\n")
        self.inv.scan()
        with self.assertRaises(JeevesAppwideError):
            self.frontier.overview()

    def test_duplicate_test_file_and_traversal_rejected(self):
        row=self.contract["journeys"][0]
        row["source_test_candidates"]=[self.name,self.name]
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.frontier.overview()
        row["source_test_candidates"]=["../../.env"]
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.frontier.overview()

    def test_policy_downgrade_and_family_target_truncation_denied(self):
        self.contract["policy"]["never_automatically_signoff"]=False
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.frontier.overview()
        self.contract["policy"]["never_automatically_signoff"]=True
        self.contract["journeys"][0]["family_ids"]=["F01"]
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.frontier.overview()

    def test_runtime_read_only_journey_catalog_and_pagination(self):
        jeeves=JeevesAppwideRuntime(self.inv)
        receipt=jeeves.invoke("ai.product.journeys",{})
        self.assertTrue(receipt["read_only_or_review_only"])
        self.assertEqual(receipt["result"]["canonical_journey_count"],12)
        self.assertFalse(receipt["result"]["actual_app_release_qualified"])
        page=jeeves.invoke("ai.product.journeys.page",{"limit":2})["result"]
        self.assertEqual(len(page["journeys"]),2)
        self.assertEqual(page["journeys"][0]["id"],"J01")
        self.assertTrue(page["release_qualification_not_claimed"])

    def test_bounded_offsets_and_boolean_pagination_fail_closed(self):
        for params in (
            {"offset":True},{"limit":False},{"limit":0},
            {"limit":50},{"offset":-1},{"offset":13},
        ):
            with self.subTest(params=params),self.assertRaises(JeevesAppwideError):
                self.frontier.page(**params)


if __name__=="__main__":
    unittest.main()
