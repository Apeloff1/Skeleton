#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
REFS={"VOL-021","VOL-022","VOL-092","VOL-093","VOL-094","VOL-095","VOL-108","VOL-109","VOL-110","VOL-115","VOL-118","VOL-119"}
class Error(RuntimeError):pass
def load(root,name):
    try:return json.loads((root/name).read_text(encoding="utf-8"))
    except Exception as exc:raise Error(f"cannot load {name}: {exc}") from exc
def req_ids(v):return [f"REQ:{v['key']}:{i:03d}" for i,_ in enumerate(v.get("requirements",[]),1)]
def validate(root=ROOT):
    root=Path(root).resolve()
    m=load(root,"machine/ai_master_plan.json");p2=load(root,"machine/ai_p2_task_backlog.json");p2m=load(root,"machine/ai_p2_execution_map.json");q=load(root,"machine/ai_build_queue.json");s=load(root,"machine/ai_master_build_sequence.json");e=load(root,"machine/ai_engineering_pass.json");em=load(root,"machine/ai_engineering_task_matrix.json");fm=load(root,"machine/ai_full_edge_case_matrix.json");a=load(root,"machine/architecture.json");ait=load(root,"machine/ai_file_tree.json");tr=load(root,"machine/master_traceability.json");c=load(root,"machine/repository_engineering_control.json")
    trace_policy=tr.get("policy",{})
    if not isinstance(trace_policy,dict):raise Error("trace policy must be an object")
    vols={v["key"]:v for v in m["volumes"]}; binds={b["volume_ref"]:b for b in c["masterplan_bindings"]}
    if set(binds)!=REFS:raise Error("masterplan binding coverage drift")
    for ref in REFS:
        v=vols[ref];b=binds[ref]
        for k,w in [("title",v["title"]),("accountability_id",v["accountability_id"]),("required_gap_texts",v["gaps"]),("risks",v["risks"]),("contracts",v["contracts"])]:
            if b.get(k)!=w:raise Error(f"{ref}.{k} drift")
    exp=[]
    for v in m["volumes"]:
        for kind,field in [("gap","gaps"),("risk","risks")]:
            for i,statement in enumerate(v.get(field,[]),1):exp.append((f"BL-{kind.upper()}-{v['key']}-{i:03d}",kind,f"{v['key']}:{kind}:{i:03d}",v["key"],statement,v["accountability_id"],req_ids(v)))
    exp.sort();rows=c["backlog"]["items"]
    if len(rows)!=len(exp):raise Error("backlog coverage drift")
    for r,w in zip(rows,exp):
        for key,val in zip(["backlog_id","source_kind","source_ref","volume_ref","statement","accountability_id","requirement_refs"],w):
            if r.get(key)!=val:raise Error(f"backlog drift {w[0]}.{key}")
        if r["state"]!="open" or r["closure_evidence_refs"]!=[]:raise Error("backlog fabricated closure/evidence")
    if c["backlog"]["summary"]["open_count"]!=len(exp) or c["backlog"]["summary"]["closed_count"]!=0:raise Error("backlog summary drift")
    if min(x["rank"] for x in c["priority"]["hard_blockers"])<500:raise Error("hard blocker priority weakened")
    for x in c["priority"]["soft_factors"]:
        if x["min"]>x["max"] or max(abs(x["min"]),abs(x["max"]))>100:raise Error("soft factor unbounded")
    if c["priority"]["percentage_is_input"] is not False or c["priority"]["anti_starvation"]["max_soft_wait_cycles"]!=c["priority"]["anti_starvation"]["forced_review_after_cycles"]:raise Error("priority gaming/starvation guard drift")
    prof={x["id"]:x for x in e["work_package_profiles"]};edge={x["id"]:x for x in fm["packages"]};waves={x["id"]:x for x in s["waves"]};pkg={x["work_package_id"]:x for x in c["work_packages"]["items"]}
    if set(pkg)!=set(m["p0_work_packages"]):raise Error("work package coverage drift")
    for pid in m["p0_work_packages"]:
        p=prof[pid];x=edge[pid];r=pkg[pid]
        expected=[]
        for kind,arr,src in [("INVARIANT",x.get("invariants",[]),"machine/ai_full_edge_case_matrix.json"),("ACCEPTANCE",x.get("acceptance",[]),"machine/ai_full_edge_case_matrix.json"),("RECOVERY",p.get("recovery_requirements",[]),"machine/ai_engineering_pass.json"),("IMPACT",p.get("change_impact_triggers",[]),"machine/ai_engineering_pass.json"),("DIMENSION",p.get("required_dimensions",[]),"machine/ai_engineering_pass.json")]:
            for i,text in enumerate(arr,1):expected.append({"requirement_id":f"WP-REQ:{pid}:{kind}:{i:03d}","kind":kind.lower(),"statement":text,"source":src})
        if r["package_requirements"]!=expected:raise Error(f"{pid} exact requirements drift")
        if pid not in waves[p["primary_wave"]]["work_packages"]:raise Error(f"{pid} wave drift")
        ts=sorted(t["task_id"] for t in em["tasks"] if pid in t.get("work_package_refs",[]))
        if r["aiq_task_ids"]!=ts:raise Error(f"{pid} AIQ binding drift")
        acc=sorted(set(t["accountability_id"] for t in em["tasks"] if t["task_id"] in ts and t.get("accountability_id")))
        if r["accountability_ids"]!=acc or r["test_targets"]!=x.get("test_targets",[]) or r["evidence_refs"]!=[]:raise Error(f"{pid} accountability/test/evidence drift")
    qt={x["task_id"]:x for x in q["tasks"]};bt={x["task_id"]:x for x in c["build_order"]["tasks"]}
    if set(qt)!=set(bt):raise Error("build order coverage drift")
    for task_id in sorted(qt):
        for field in ("status","stage","task_dependencies","closure_dependencies","work_package_refs","accountability_id","target_paths"):
            if bt[task_id].get(field)!=qt[task_id].get(field):raise Error(f"build order task drift {task_id}.{field}")
    visiting=set();visited=set()
    def visit(t):
        if t in visited:return
        if t in visiting:raise Error(f"dependency cycle {t}")
        visiting.add(t)
        for d in bt[t]["task_dependencies"]:
            if d not in bt:raise Error(f"unknown task dependency {d}")
            visit(d)
        visiting.remove(t);visited.add(t)
    for t in sorted(bt):visit(t)
    if len(c["build_order"]["topological_order"])!=len(qt) or set(c["build_order"]["topological_order"])!=set(qt):raise Error("topological order drift")
    order=c["build_order"]["topological_order"];positions={task_id:i for i,task_id in enumerate(order)}
    for task_id,row in bt.items():
        for dep in row["task_dependencies"]:
            if positions[dep]>=positions[task_id]:raise Error(f"topological order violates dependency {dep}->{task_id}")
    if c["definition_of_done"]["closure_chain"]!=e["closure_chain"] or len(c["definition_of_done"]["non_compensable"])<6:raise Error("DoD drift")
    if "zero completion authority" not in c["completion"]["aggregation"]["percentage"]:raise Error("completion percentage authority drift")
    if c["completion"].get("derivation_engine")!="skeleton/repo_machine/completion.py":raise Error("completion derivation engine drift")
    inv=c["completion"].get("change_impact_invalidation",{})
    if inv.get("trace_graph")!="machine/master_traceability.json" or inv.get("checker")!="scripts/check_trace_pr_impact.py":raise Error("completion invalidation authority drift")
    if trace_policy.get("impact_rule") is None:raise Error("trace impact rule missing")
    snaps={x["task_id"]:x for x in c["completion"]["p2_task_snapshot"]};p2t={x["task_id"]:x for x in p2["tasks"]}
    if set(snaps)!=set(p2t):raise Error("P2 completion snapshot drift")
    for tid,t in p2t.items():
        r=snaps[tid]
        if r["declared_status"]!=t["status"] or r["implementation_signed"]!=t["implementation_signed"] or r["verification_signed"]!=t["verification_signed"] or r["completion_checkbox"]!=t["completion_checkbox"]:raise Error(f"{tid} completion source drift")
        if t["implementation_signed"] and t["verification_signed"] and t["completion_checkbox"]:expected_state="verified_complete"
        elif t["status"]=="landed_unpromoted":expected_state="evidence_pending"
        elif t["status"]=="in_progress":expected_state="in_progress"
        elif t["status"]=="blocked":expected_state="blocked"
        elif t["status"]=="ready":expected_state="not_started"
        else:raise Error(f"{tid} unsupported P2 task status {t['status']!r}")
        if r["derived_state"]!=expected_state:raise Error(f"{tid} completion derived-state drift")
    bids={x["backlog_id"] for x in rows}
    for d in c["debt"]:
        if not d["debt_id"].startswith("DEBT-") or not d["owner"] or not set(d["backlog_refs"])<=bids:raise Error("debt binding drift")
    td=next(x for x in c["debt"] if x["debt_id"]=="DEBT-P2-TRACE-EVIDENCE")
    if td["interest_metric"]["value"]!=tr["summary"]["requirements_without_evidence"]:raise Error("trace debt count drift")
    canon={x["id"]:x for x in a["canonical_roots"]};roots={x["root_id"]:x for x in c["maintenance"]["roots"]}
    expected_maintenance_checks=["canonical owner resolved","trace reachability checked","retention/evidence hold clear","migration/cutover safe","regeneration authority known","rollback/recovery recorded"]
    if set(canon)!=set(roots) or c["maintenance"]["deletion_default"]!="deny" or c["maintenance"]["required_checks"]!=expected_maintenance_checks:raise Error("maintenance policy drift")
    if c["maintenance"].get("decision_engine")!="skeleton/repo_machine/maintenance.py":raise Error("maintenance decision engine drift")
    trace_authority=c["maintenance"].get("trace_authority",{})
    if trace_authority.get("graph")!="machine/master_traceability.json" or trace_authority.get("checker")!="scripts/check_trace_pr_impact.py" or trace_authority.get("impact_rule")!=trace_policy.get("impact_rule"):raise Error("maintenance trace authority drift")
    for rid,x in canon.items():
        if roots[rid]["path"]!=x["path"] or roots[rid]["owner"]!=x["owner"]:raise Error(f"maintenance owner drift {rid}")
    for p in c["anti_patterns"]:
        if not(root/p["detector"]).is_file():raise Error("anti-pattern detector drift")
        if p["exception_allowed"] is False and p.get("max_exception_ttl_days") is not None:raise Error("non-waivable anti-pattern has TTL")
        if p["exception_allowed"] is True:
            ttl=p.get("max_exception_ttl_days")
            if not isinstance(ttl,int) or isinstance(ttl,bool) or ttl<=0 or ttl>90:raise Error("waivable anti-pattern TTL drift")
    apx=c.get("anti_pattern_exception_policy",{})
    if apx.get("validator")!="skeleton/repo_machine/anti_patterns.py" or apx.get("default")!="deny" or not isinstance(apx.get("exceptions"),list):raise Error("anti-pattern exception policy drift")
    required_apx={"exception_id","pattern_id","owner_id","rationale","created_at_utc","expires_at_utc","evidence_refs"}
    if set(apx.get("required_fields",[]))!=required_apx:raise Error("anti-pattern exception required fields drift")
    if c["roadmap"]["lanes"]!=p2m["lanes"]:raise Error("roadmap lane drift")
    roadmap_items={x["task_id"]:x for x in c["roadmap"]["items"]}
    if set(roadmap_items)!=set(p2t):raise Error("roadmap coverage drift")
    roadmap_authority="signed evidence/accountability; roadmap state alone has no authority"
    for task_id,task in p2t.items():
        expected={"roadmap_id":f"ROADMAP-{task_id}","task_id":task_id,"lane_id":task["lane_id"],"status":task["status"],"depends_on":task["depends_on"],"volume_refs":task["primary_volume_refs"],"completion_authority":roadmap_authority}
        if roadmap_items[task_id]!=expected:raise Error(f"roadmap task drift {task_id}")
    revisions=c["roadmap"].get("revisions",[])
    if not revisions or len({x.get("revision_id") for x in revisions})!=len(revisions):raise Error("roadmap revision lineage drift")
    if any(x.get("preserves_history") is not True for x in revisions):raise Error("roadmap revision history weakened")
    if revisions[-1].get("source")!=f"machine/ai_p2_execution_map.json@{p2m['map_version']}":raise Error("roadmap current-map revision drift")
    for k in ["enabled","last_top_level_volume","exception_register"]:
        if c["roadmap"]["breadth_freeze"][k]!=m["breadth_freeze"][k]:raise Error("breadth freeze drift")
    runtime_controls=c.get("runtime_controls",{})
    expected_controls={"transaction","independent_review","code_index","maintenance","priority","completion","anti_patterns"}
    if set(runtime_controls)!=expected_controls:raise Error("runtime control coverage drift")
    for name,item in runtime_controls.items():
        src=item.get("canonical");mir=item.get("mirror");test=item.get("tests")
        if not all(isinstance(x,str) and x for x in (src,mir,test)):raise Error(f"runtime control path drift {name}")
        if not (root/src).is_file() or not (root/mir).is_file() or not (root/test).is_file():raise Error(f"runtime control file missing {name}")
        if (root/src).read_bytes()!=(root/mir).read_bytes():raise Error(f"mirror drift {src}")
        if not isinstance(item.get("guarantees"),list) or not item["guarantees"]:raise Error(f"runtime control guarantees missing {name}")
    maprow=next(x for x in ait["mappings"] if x.get("id")=="AIFT-REPO-MACHINE")
    if maprow["source"]!="skeleton/repo_machine" or maprow["destination"]!="skeleton/ai/build/repo_machine":raise Error("AI-tree repo-machine mapping drift")
    return {"status":"valid","masterplan_bindings":len(binds),"backlog_items":len(rows),"work_packages":len(pkg),"package_requirements":sum(len(x["package_requirements"]) for x in pkg.values()),"aiq_tasks":len(qt)}
def main():
    p=argparse.ArgumentParser();p.add_argument("--repo-root",default=".");p.add_argument("--json",action="store_true");a=p.parse_args()
    try:r=validate(Path(a.repo_root))
    except Error as exc:print(f"p2 repository engineering: FAIL: {exc}",file=sys.stderr);return 1
    print(json.dumps(r,sort_keys=True) if a.json else r);return 0
if __name__=="__main__":raise SystemExit(main())
