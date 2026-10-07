from __future__ import annotations
import importlib.util,json,shutil,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
S=importlib.util.spec_from_file_location("p2repo",ROOT/"scripts/check_p2_repository_engineering.py");assert S and S.loader
M=importlib.util.module_from_spec(S);S.loader.exec_module(M)
class T(unittest.TestCase):
 def test_current(self):
  r=M.validate(ROOT);self.assertEqual(r["status"],"valid");self.assertEqual(r["masterplan_bindings"],12);self.assertGreater(r["backlog_items"],1000);self.assertEqual(r["work_packages"],31);self.assertGreater(r["package_requirements"],100)
 def fixture(self):
  t=Path(tempfile.mkdtemp(prefix="p2repo-"));self.addCleanup(lambda:shutil.rmtree(t,ignore_errors=True))
  names=["ai_master_plan","ai_p2_task_backlog","ai_p2_execution_map","ai_build_queue","ai_master_build_sequence","ai_engineering_pass","ai_engineering_task_matrix","ai_full_edge_case_matrix","architecture","ai_file_tree","master_traceability","repository_engineering_control"]
  paths=[f"machine/{x}.json" for x in names]
  c=json.loads((ROOT/"machine/repository_engineering_control.json").read_text())
  for item in c["runtime_controls"].values():
   paths.extend((item["canonical"],item["mirror"],item["tests"]))
  paths += [x["detector"] for x in c["anti_patterns"]]
  for rel in sorted(set(paths)):
   src=ROOT/rel;dst=t/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
  return t
 def test_backlog_loss(self):
  r=self.fixture();p=r/"machine/repository_engineering_control.json";d=json.loads(p.read_text());d["backlog"]["items"].pop();p.write_text(json.dumps(d))
  with self.assertRaisesRegex(M.Error,"backlog coverage"):M.validate(r)
 def test_false_closure(self):
  r=self.fixture();p=r/"machine/repository_engineering_control.json";d=json.loads(p.read_text());d["backlog"]["items"][0]["state"]="closed";p.write_text(json.dumps(d))
  with self.assertRaisesRegex(M.Error,"fabricated closure"):M.validate(r)
 def test_priority_escape(self):
  r=self.fixture();p=r/"machine/repository_engineering_control.json";d=json.loads(p.read_text());d["priority"]["soft_factors"][0]["max"]=2000;p.write_text(json.dumps(d))
  with self.assertRaisesRegex(M.Error,"unbounded"):M.validate(r)
 def test_build_order_cannot_narrow_canonical_dependency(self):
  r=self.fixture();p=r/"machine/repository_engineering_control.json";d=json.loads(p.read_text());task=next(x for x in d["build_order"]["tasks"] if x["task_dependencies"]);task["task_dependencies"]=[];p.write_text(json.dumps(d))
  with self.assertRaisesRegex(M.Error,"build order task drift"):M.validate(r)
 def test_topological_order_dependency_violation(self):
  r=self.fixture();p=r/"machine/repository_engineering_control.json";d=json.loads(p.read_text());order=d["build_order"]["topological_order"];tasks={x["task_id"]:x for x in d["build_order"]["tasks"]}
  task_id=next(t for t in order if tasks[t]["task_dependencies"]);dep=tasks[task_id]["task_dependencies"][0];i=order.index(dep);j=order.index(task_id);order[i],order[j]=order[j],order[i];p.write_text(json.dumps(d))
  with self.assertRaisesRegex(M.Error,"topological order violates dependency"):M.validate(r)
 def test_false_complete(self):
  r=self.fixture();p=r/"machine/repository_engineering_control.json";d=json.loads(p.read_text());d["completion"]["p2_task_snapshot"][0]["derived_state"]="verified_complete";p.write_text(json.dumps(d))
  with self.assertRaisesRegex(M.Error,"completion derived-state drift"):M.validate(r)
 def test_trace_policy_missing(self):
  r=self.fixture();p=r/"machine/master_traceability.json";d=json.loads(p.read_text());d.setdefault("policy",{}).pop("impact_rule",None);p.write_text(json.dumps(d))
  with self.assertRaisesRegex(M.Error,"trace impact rule missing"):M.validate(r)
 def test_completion_snapshot_cannot_drift_from_p2_status(self):
  r=self.fixture();p=r/"machine/repository_engineering_control.json";d=json.loads(p.read_text());d["completion"]["p2_task_snapshot"][0]["declared_status"]="in_progress";d["completion"]["p2_task_snapshot"][0]["derived_state"]="in_progress";p.write_text(json.dumps(d))
  with self.assertRaisesRegex(M.Error,"completion source drift"):M.validate(r)
 def test_roadmap_revision_must_track_current_p2_map(self):
  r=self.fixture();p=r/"machine/repository_engineering_control.json";d=json.loads(p.read_text());d["roadmap"]["revisions"][-1]["source"]="machine/ai_p2_execution_map.json@stale";p.write_text(json.dumps(d))
  with self.assertRaisesRegex(M.Error,"current-map revision drift"):M.validate(r)
 def test_roadmap_cannot_drift_from_p2_backlog(self):
  r=self.fixture();p=r/"machine/repository_engineering_control.json";d=json.loads(p.read_text());d["roadmap"]["items"][0]["status"]="blocked";p.write_text(json.dumps(d))
  with self.assertRaisesRegex(M.Error,"roadmap task drift"):M.validate(r)
 def test_mirror_drift(self):
  r=self.fixture();p=r/"skeleton/ai/build/repo_machine/review.py";p.write_text(p.read_text()+"\n# drift")
  with self.assertRaisesRegex(M.Error,"mirror drift"):M.validate(r)
if __name__=="__main__":unittest.main()
