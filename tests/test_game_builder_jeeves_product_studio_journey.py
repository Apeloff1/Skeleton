"""Real loopback Studio operator journey for Jeeves acceptance evidence.

Exercises the HTTP control plane, access control, bounded cursor agreement,
actual temporary filesystem sources and persistence-inert product readings.
This proves one *local* integration subset only, never installed product,
trained model quality, or an independent release-device qualification.
"""
from __future__ import annotations

import http.client
from hashlib import sha256
import json
from pathlib import Path
import threading
import unittest

from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
from tests.test_game_builder_jeeves_completion_census import CompletionCensusTests


class StudioMeasuredUserJourneyTests(unittest.TestCase):
    def setUp(self):
        self.fixture=CompletionCensusTests(
            "test_sources_and_declared_maturity_never_certify_product")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.root
        self.scope={
            "schema":"skeleton.ai.app_completion_scope.v1",
            "stages":[{
                "id":k,"source_auto_measure":i==0,
                "definition":"independent acceptance not assumed"}
                for i,k in enumerate((
                    "source_owner","implementation_test","runtime_integration",
                    "user_journey","release_device"))],
            "evidence_policy": {k:True for k in (
                "source_presence_is_not_functionality","unknown_must_remain_unknown",
                "never_infer_ci_from_workflow_file",
                "never_promote_planned_volume_signatures",
                "independent_evidence_required",
                "regression_invalidates_accepted_receipts")},
            "families":[{
                "id":"F%02d"%i,"title":"Product family %02d"%i,
                "domain":"ai","owner":"skeleton/ai",
                "source_roots":["backend/server.py"],
                "acceptance_target":"Real functionality must be independently proven",
                "required_proof":[
                    "source_owner","implementation_test","runtime_integration",
                    "user_journey","release_device"],
                "risk_weight":1,
            } for i in range(1,43)],
        }
        self.module="tests.test_game_builder_studio_journey_fixture"
        self.test_path=self.module.replace(".","/")+".py"
        self.fixture.put(self.test_path,
                         "import unittest\nclass Actual(unittest.TestCase):\n"
                         "    def test_real(self): self.assertTrue(True)\n")
        self.mapping={
            "schema":"skeleton.ai.app_acceptance_test_matrix.v1",
            "parent_scope":"machine/app_completion_scope.json",
            "stage":"implementation_test",
            "runner_mode":"unittest_module_exact_head",
            "policies":{key:True for key in (
                "requires_real_test_execution","exact_commit_required",
                "source_test_sha_receipts_required",
                "no_success_inference_from_file_presence",
                "matrix_does_not_verify_end_to_end_user_journey",
                "automated_model_or_source_promotion_forbidden",
                "unmapped_families_remain_unknown")},
            "bindings":[{
                "family_id":"F13",
                "scope":"targeted_regression_subset",
                "execution_tier":"ci_smoke",
                "independent_acceptance_question":
                    "Can Studio access the reviewed evidence registry with a real operator token?",
                "unittest_modules":[self.module],
                "product_release_qualified":False,
            }],
        }
        self.fixture.put("machine/app_completion_scope.json",
                         json.dumps(self.scope,sort_keys=True))
        self.fixture.put("machine/app_acceptance_test_matrix.json",
                         json.dumps(self.mapping,sort_keys=True))
        self.fixture.put("machine/p1_required_gate_authority.json",
                         json.dumps({"gates":[{"id":"GATE-001",
                         "required_for_terminal_p1_promotion":True}]}))
        self.fixture.inv.scan()
        self.workspace=GameWorkspace.create(
            str(self.root/"integration_workbench"),authorized=True)
        self.workspace.create_project(
            "original_story_world","rpg",authorized=True)
        self.server=create_workspace_server(
            self.workspace,port=0,repo_root=self.root)
        self.thread=threading.Thread(
            target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self._close)

    def _close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=4)

    def request(self,method,path,body=None,*,authenticated=True,origin=None):
        connection=http.client.HTTPConnection(
            "127.0.0.1",self.server.server_port,timeout=12)
        headers={"Host":f"127.0.0.1:{self.server.server_port}"}
        if authenticated:
            headers["X-Game-Studio-Token"]=self.server.secret
        if body is not None:
            headers["Content-Type"]="application/json"
        if origin is not None:
            headers["Origin"]=origin
        try:
            connection.request(
                method,path,
                body=json.dumps(body) if body is not None else None,
                headers=headers)
            response=connection.getresponse()
            result=response.status,response.read()
            try:
                return result[0],json.loads(result[1])
            except (ValueError,UnicodeDecodeError):
                return result
        finally:
            connection.close()

    def invoke(self,action,params=None,**kwargs):
        return self.request("POST","/api/jeeves-appwide-invoke",{
            "action":action,"params":params or {},**kwargs})

    def test_operator_can_measure_and_inspect_real_registered_test_sources(self):
        status,body=self.request("GET","/api/jeeves-appwide-catalog")
        self.assertEqual(status,200)
        self.assertIn("ai.product.measure",
                      json.dumps(body))
        status,measure=self.invoke("ai.product.measure")
        self.assertEqual(status,200)
        overview=measure["result"]
        self.assertEqual(overview["family_count"],42)
        self.assertEqual(overview["family_static_source_located"],42)
        self.assertEqual(overview["source_presence_percent"],100.0)
        self.assertIsNone(overview["full_app_completion_percent"])
        self.assertEqual(overview["unknown_independent_acceptance_stages"],168)
        status,matrix=self.invoke("ai.product.tests")
        self.assertEqual(status,200)
        self.assertEqual(matrix["result"]["curated_test_family_count"],1)
        self.assertEqual(matrix["result"]["unique_static_test_case_count"],1)
        self.assertEqual(matrix["result"]["tests_executed_by_this_reader"],0)
        self.assertIsNone(matrix["result"]["exact_head_passed_from_source_scan"])
        status,page=self.invoke("ai.product.tests.page",{
            "limit":1,"expected_matrix_digest":matrix["result"]["digest"]})
        self.assertEqual(status,200)
        self.assertEqual(page["result"]["families"][0]["family_id"],"F13")
        self.assertFalse(page["result"]["families"][0]["release_device_qualified"])

    def test_bounded_pages_and_unknown_families_remain_unqualified(self):
        status,overview=self.invoke("ai.product.measure")
        self.assertEqual(status,200)
        digest=overview["result"]["digest"]
        all_pages=[]
        offset=0
        while True:
            status,page=self.invoke("ai.product.measure.page",{
                "offset":offset,"limit":13,
                "expected_measurement_digest":digest})
            self.assertEqual(status,200)
            all_pages.extend(item["id"] for item in page["result"]["families"])
            offset=page["result"]["next_offset"]
            if offset is None:
                break
        self.assertEqual(all_pages,["F%02d"%i for i in range(1,43)])
        self.assertEqual(len(all_pages),len(set(all_pages)))
        status,missing=self.invoke("ai.product.tests.page",{
            "only_unmapped":True,"limit":6})
        self.assertEqual(status,200)
        self.assertEqual(missing["result"]["total_matches"],41)
        self.assertTrue(all(x["missing_curated_tests"]
                            for x in missing["result"]["families"]))

    def test_untrusted_requests_cannot_read_or_promote_app_evidence(self):
        body={"action":"ai.product.measure","params":{}}
        self.assertEqual(self.request(
            "POST","/api/jeeves-appwide-invoke",body,
            authenticated=False)[0],403)
        self.assertEqual(self.request(
            "POST","/api/jeeves-appwide-invoke",body,
            origin="https://untrusted-origin.example")[0],403)
        self.assertEqual(self.invoke("shell.execute",{
            "command":"whoami"})[0],400)
        status,receipt=self.invoke("ai.product.measure",{
            "source_auto_measure":True},operator_authorized=True)
        self.assertEqual(status,400)
        self.assertNotIn("release_qualified",json.dumps(receipt).lower())

    def test_stale_report_cannot_be_replayed_after_source_contract_change(self):
        status,overview=self.invoke("ai.product.measure")
        self.assertEqual(status,200)
        old=overview["result"]["digest"]
        # Changing source contract is a simulated independent repo edit; the
        # Jeeves observer itself must never perform this change.
        scope=Path(self.root/"machine/app_completion_scope.json")
        content=scope.read_text()
        scope.write_text(content.replace("Product family 01","Product family 1A"))
        # The already-indexed inventory is intentionally stale until rescanned.
        # The accepted content lease must reject the changed review contract.
        status,page=self.invoke("ai.product.measure.page",{
            "limit":1,"expected_measurement_digest":old})
        self.assertEqual(status,400)
        self.assertNotIn("verified",json.dumps(page).lower())

    def test_actual_studio_read_requests_do_not_modify_project_source(self):
        project=self.root/"integration_workbench/current/original_story_world/project.json"
        before=sha256(project.read_bytes()).hexdigest()
        for operation in ("ai.product.measure","ai.product.tests",
                          "ai.product.measure.page","ai.product.tests.page"):
            status,response=self.invoke(operation)
            self.assertEqual(status,200,operation+" "+str(response)[:200])
        self.assertEqual(sha256(project.read_bytes()).hexdigest(),before)
        self.assertEqual(self.workspace.active(),"original_story_world")


if __name__ == "__main__":
    unittest.main()
