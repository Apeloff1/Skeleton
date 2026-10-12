"""Adversarial, runtime-backed Jeeves whole-app capability and editor tests."""
from __future__ import annotations

from copy import deepcopy
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from skeleton.ai.game_builder.jeeves_app_runtime import (
    app_atlas,dispatch_app_action,JeevesAppCapabilityError,
    ACTIONS,SURFACES)
from skeleton.ai.game_builder.system_editors import catalog


class JeevesAllAppCapabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work=GameWorkspace.create(str(Path(self.temp.name)/"original"),authorized=True)
        self.work.create_project("new_world","rpg",authorized=True)
        self.project="new_world"

    def call(self,action,args=None,authorized=False):
        return dispatch_app_action(self.work,self.project,action,
                                   {} if args is None else args,
                                   authorized=authorized)

    def test_source_taxonomy_is_real_and_does_not_claim_every_module_executable(self):
        result=app_atlas()
        self.assertGreaterEqual(result["family_count"],25)
        self.assertGreaterEqual(result["typed_game_editor_count"],40)
        self.assertGreaterEqual(len(result["operator_adapters"]),18)
        self.assertFalse(result["all_source_modules_executable"])
        self.assertEqual(result["digest"],app_atlas()["digest"])
        self.assertGreaterEqual(len(SURFACES),25)
        family=app_atlas(family="studio",offset=0,limit=20)
        self.assertGreaterEqual(family["total_entries"],100)
        self.assertTrue(family["entries"])
        self.assertTrue(all(not e["execution_adapter"] for e in family["entries"]))
        page=app_atlas(family="studio",offset=20,limit=20)
        self.assertNotEqual(page["entries"],family["entries"])
        self.assertEqual(page["total_entries"],family["total_entries"])
        self.assertEqual(self.call("atlas.summary")["result"]["family_count"],
                         result["family_count"])
        self.assertTrue(any(row["name"]=="studio_execution_plane.py" for row
                            in app_atlas(family="studio",query="execution",
                                         limit=20)["entries"]))
        with self.assertRaises(JeevesAppCapabilityError):
            app_atlas(family="completely_undiscovered_root")
        with self.assertRaises(JeevesAppCapabilityError):
            app_atlas(family="studio",query="../skeleton/vault")
        with self.assertRaises(JeevesAppCapabilityError):
            app_atlas(family="studio",limit=999999)

    def test_nested_installed_filetree_is_indexed_without_executing_modules(self):
        result=self.call("atlas.deep",{
            "family":"studio","query":None,
            "offset":0,"limit":80,"max_depth":3})["result"]
        self.assertGreaterEqual(result["matching_entries"],100)
        self.assertTrue(all(not x["local_execution_adapter_granted"]
                            for x in result["entries"]))
        subset=self.call("atlas.deep",{
            "family":"studio","query":"story_canon",
            "offset":0,"limit":20,"max_depth":3})["result"]
        self.assertTrue(any("story_canon_fabric.py" in x["path"]
                            for x in subset["entries"]))
        with self.assertRaises(JeevesAppCapabilityError):
            self.call("atlas.deep",{
                "family":"studio","query":"../secrets",
                "offset":0,"limit":80,"max_depth":3})
        with self.assertRaises(JeevesAppCapabilityError):
            self.call("atlas.deep",{
                "family":"studio","query":None,
                "offset":0,"limit":80,"max_depth":100})

    def test_real_original_game_builds_are_replay_proved_and_source_only(self):
        intent={"title":"Original Lantern Investigation",
                "subtitle":"A new game built from reviewed original intent",
                "seed":42,"width":9,"height":9,"levels":1,
                "collectibles_per_level":1,"hazards_per_level":0,
                "theme":"forest","starting_health":3}
        self.assertIn("game.compile.original",ACTIONS)
        with self.assertRaises(PermissionError):
            self.call("game.compile.original",{"intent":intent})
        browser=self.call("game.compile.original",{"intent":intent},authorized=True)
        self.assertTrue(browser["result"]["gameplay_proof_executed"])
        self.assertEqual(browser["result"]["compiled_source_receipt"]["levels"],1)
        self.assertTrue(browser["result"]["compiled_source_receipt"]
                        ["validated_gameplay_proof"])
        self.assertFalse(browser["result"]["source_exported_to_disk"])
        self.assertFalse(browser["result"]["consumer_release_certified"])
        native=self.call("game.compile.native",{"intent":intent},authorized=True)
        self.assertEqual(native["result"]["browser_html_sha256"],
                         browser["result"]["browser_html_sha256"])
        self.assertRegex(native["result"]["native_source_manifest_digest"],
                         r"^[a-f0-9]{64}$")
        self.assertFalse(native["result"]["native_godot_executable_executed"])
        with self.assertRaises(ValueError):
            self.call("game.compile.original",{"intent":{**intent,"width":8}},
                      authorized=True)
        with self.assertRaises(ValueError):
            self.call("game.compile.original",{"intent":{**intent,"levels":8}},
                      authorized=True)
        with self.assertRaises(JeevesAppCapabilityError):
            self.call("game.compile.native",{"intent":{**intent,
                "project_id":"different_project"}},authorized=True)
        self.assertFalse(any(x.path.startswith("systems/") for x in
                             self.work.files("current",self.project)))

    def test_all_actual_editors_have_typed_context_and_can_be_previewed(self):
        all_systems=catalog()
        self.assertGreaterEqual(len(all_systems),40)
        for entry in all_systems:
            with self.subTest(editor=entry["id"]):
                observed=self.call("atlas.editor",{"editor":entry["id"]})["result"]
                self.assertEqual(observed["id"],entry["id"])
                response=self.call("studio.editor.preview",{
                    "editor":entry["id"],"settings":{}})["result"]
                self.assertEqual(response["editor"],entry["id"])
                self.assertIn("simulation_executed",response)
                self.assertIn(response["status"],("authoring_only",
                                                   "deterministic_prototype"))
        self.assertEqual([x.path for x in self.work.files("current",self.project)
                          if x.path.startswith("systems/")],[])
        with self.assertRaises(ValueError):
            self.call("studio.editor.preview",{"editor":"shell.exec","settings":{}})
        with self.assertRaises(ValueError):
            self.call("studio.editor.preview",{
                "editor":all_systems[0]["id"],"settings":{"unregistered":1}})

    def test_all_editor_changes_require_real_human_review_and_exact_source_head(self):
        args={
            "editor":"racing",
            "settings":{"laps":3},
            "reason":"Author a reviewed original racing game with three laps.",
        }
        with self.assertRaises(PermissionError):
            self.call("studio.editor.stage",args)
        ready=self.call("studio.editor.stage",args,authorized=True)
        self.assertFalse(ready["source_files_committed"])
        self.assertTrue(ready["result"]["human_commit_required"])
        self.assertEqual(self.work.files("current",self.project),[])
        with self.assertRaises(PermissionError):
            self.work.commit(ready["result"]["proposal_id"],human_approved=False,
                             authorized=True)
        self.work.commit(ready["result"]["proposal_id"],human_approved=True,
                         authorized=True)
        self.assertEqual(len(self.work.files("current",self.project)),1)
        with self.assertRaises(JeevesAppCapabilityError):
            self.call("studio.editor.stage",{
                **args,"reason":"short"},authorized=True)
        with self.assertRaises(JeevesAppCapabilityError):
            self.call("studio.editor.stage",{
                "editor":"racing","settings":{"laps":3},
                "reason":"This valid reason should not have extra arguments.",
                "shell":"rm -rf /"},authorized=True)

    def test_source_scope_denies_private_paths_and_foreign_projects(self):
        with self.assertRaises(PermissionError):
            self.call("studio.source",{"path":"../../etc/passwd"})
        with self.assertRaises(PermissionError):
            self.call("studio.source",{"path":"game/session_secret.json"})
        with self.assertRaises(PermissionError):
            self.call("studio.source",{"path":"skeleton/ai/provider_runtime.py"})
        with self.assertRaises(JeevesAppCapabilityError):
            dispatch_app_action(self.work,"different_project","studio.tree",{})
        with self.assertRaises(JeevesAppCapabilityError):
            self.call("__import__",{})
        with self.assertRaises(JeevesAppCapabilityError):
            self.call("studio.tree",{"ignored":True})
        self.assertEqual(self.call("studio.tree")["action"],"studio.tree")

    def test_real_universal_forge_graph_checks_ports_types_and_cycles(self):
        components=[
            {"id":"origin","kind":"source","config":{}},
            {"id":"observer","kind":"transform","config":{}},
            {"id":"output","kind":"sink","config":{}},
        ]
        correct={
            "name":"Original deterministic game event pathway",
            "components":components,
            "wires":[["origin","out","observer","in"],
                     ["observer","out","output","in"]],
        }
        good=self.call("forge.graph",correct)
        self.assertTrue(good["result"]["valid"])
        self.assertEqual(good["result"]["component_count"],3)
        self.assertFalse(good["result"]["game_build_executed"])
        self.assertEqual(good["digest"],self.call("forge.graph",correct)["digest"])
        incorrect={**correct,"wires":[["origin","out","observer","not_a_port"]]}
        bad=self.call("forge.graph",incorrect)["result"]
        self.assertFalse(bad["valid"])
        self.assertTrue(bad["problems"])
        cycle={
            "name":"Engine dependency cycle",
            "components":[{"id":"a","kind":"transform","config":{}},
                          {"id":"b","kind":"transform","config":{}}],
            "wires":[["a","out","b","in"],["b","out","a","in"]],
        }
        self.assertFalse(self.call("forge.graph",cycle)["result"]["valid"])
        with self.assertRaises(JeevesAppCapabilityError):
            self.call("forge.graph",{**correct,"components":[
                {"id":"executable","kind":"shell_exec","config":{}}]})
        self.assertIn("source",self.call("forge.kinds")["result"]["component_kinds"])

    def test_existing_typed_tool_fabric_is_discoverable_but_not_autonomous(self):
        tools=self.call("tool.fabric")["result"]["tools"]
        self.assertGreaterEqual(len(tools),15)
        self.assertTrue(any(t["tool_id"]=="world.generate" and
                            t["local_executor_present"] for t in tools))
        self.assertTrue(all(t["model_may_execute_without_operator"] is False
                            for t in tools))
        plan={"phase":"original","tools":["world.generate"],
              "input_digest":"a"*64,
              "rationale":"Construct a bounded original reviewed game world."}
        with self.assertRaises(PermissionError):
            self.call("tool.plan",plan)
        proposed=self.call("tool.plan",plan,authorized=True)["result"]
        self.assertFalse(proposed["execution_performed"])
        self.assertEqual(proposed["locally_executable_tools"],["world.generate"])
        with self.assertRaises(ValueError):
            self.call("tool.plan",{**plan,"tools":["unknown.execute"]},
                      authorized=True)
        with self.assertRaises(ValueError):
            self.call("tool.plan",{**plan,"input_digest":"invalid"},authorized=True)

    def test_companion_dragon_rehearsal_cannot_grant_network_or_memory_approval(self):
        observed=self.call("companion.simulate",{
            "owner":"user",
            "events":[{"event":"wake"},{"event":"talk"},{"event":"rest"}],
        })["result"]
        self.assertEqual([p["phase"] for p in observed["phases"]],
                         ["listening","listening","resting"])
        self.assertFalse(observed["real_network_crawl_performed"])
        self.assertFalse(observed["memory_or_weights_promoted"])
        with self.assertRaises(PermissionError):
            self.call("companion.simulate",{"owner":"user","events":[
                {"event":"wake"},
                {"event":"start_research","topic":"game engines","consent":False}]})
        with self.assertRaises(PermissionError):
            self.call("companion.simulate",{"owner":"user","events":[
                {"event":"approved"}]})
        with self.assertRaises(ValueError):
            self.call("companion.simulate",{"owner":"user","events":[
                {"event":"wake","shell":"echo nope"}]})

    def test_crawler_and_model_learning_are_exposed_but_not_promoted(self):
        response=self.call("crawler.catalog",{"offset":0,"limit":100})["result"]
        self.assertGreaterEqual(response["total_entries"],100)
        self.assertTrue(any("dragon" in x["name"] for x in response["entries"]))
        args={
            "target_family":"model_runtime",
            "baseline_sha256":"1"*64,"candidate_sha256":"2"*64,
            "hypothesis":"A smaller adapter should lower latency at equal gameplay quality.",
            "metrics":["frozen story holdout accuracy","scene delivery p95 latency"],
            "rollback_plan":"Restore the existing content-addressed champion baseline.",
        }
        result=self.call("model.improvement",args)["result"]
        self.assertFalse(result["weight_promotion_performed"])
        self.assertFalse(result["runtime_self_modification_performed"])
        self.assertIn("adversarial_mirror",result["required_independent_gates"])
        with self.assertRaises(JeevesAppCapabilityError):
            self.call("model.improvement",{**args,"candidate_sha256":"1"*64})
        with self.assertRaises(JeevesAppCapabilityError):
            self.call("model.improvement",{**args,"target_family":"unknown"})

    def test_studio_http_api_and_ui_obey_token_and_review_boundaries(self):
        server=create_workspace_server(self.work,port=0)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            def request(method,route,payload=None,*,token=True,origin=None):
                conn=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=15)
                headers={"Host":f"127.0.0.1:{server.server_port}"}
                if token:headers["X-Game-Studio-Token"]=server.secret
                if payload is not None:
                    headers["Content-Type"]="application/json"
                    if origin is not None:headers["Origin"]=origin
                conn.request(method,route,json.dumps(payload) if payload is not None else None,
                             headers)
                response=conn.getresponse()
                status=response.status
                body=json.loads(response.read())
                conn.close()
                return status,body
            self.assertEqual(request("GET","/api/jeeves-app-atlas",token=False)[0],403)
            status,atlas=request("GET","/api/jeeves-app-atlas")
            self.assertEqual(status,200)
            self.assertGreaterEqual(atlas["typed_game_editor_count"],40)
            self.assertEqual(request("POST","/api/jeeves-app-action",{
                "project":self.project,"action":"studio.tree","args":{}},
                token=False)[0],403)
            self.assertEqual(request("POST","/api/jeeves-app-action",{
                "project":self.project,"action":"studio.tree","args":{}},
                origin="https://evil.example")[0],403)
            status,response=request("POST","/api/jeeves-app-action",{
                "project":self.project,"action":"studio.editor.preview",
                "args":{"editor":"racing","settings":{"laps":3}}})
            self.assertEqual(status,200)
            self.assertEqual(response["result"]["editor"],"racing")
            self.assertEqual(request("POST","/api/jeeves-app-action",{
                "project":self.project,"action":"model.improvement","args":{
                    "target_family":"models","baseline_sha256":"a"*64,
                    "candidate_sha256":"a"*64,"hypothesis":"wrong",
                    "metrics":["not enough"],"rollback_plan":"missing"}})[0],400)
            html=render_workspace_html("Z"*32).decode()
            for marker in ('id="jeeves-app-action"','id="jeeves-app-use-editor"',
                           "Whole-App Capability Cockpit","/api/jeeves-app-action",
                           "studio.editor.stage","model.improvement"):
                self.assertIn(marker,html)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__=="__main__":
    unittest.main()
