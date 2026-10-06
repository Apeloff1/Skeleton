#!/usr/bin/env python3
from __future__ import annotations

import argparse, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "machine" / "essentials_1000.json"
SCHEDULER = ROOT / "machine" / "project_self_improvement_idle_scheduler.json"
CLOSURE = ROOT / "machine" / "essentials_1000_closure_protocol.json"
LEDGER = ROOT / "machine" / "essentials_1000_gap_ledger.json"

MATURITY = ["planned","specified","implemented","integrated","independently_verified","signed_complete"]

def validate_closure_protocol(protocol: dict) -> list[str]:
    errors: list[str] = []
    if protocol.get("schema_version") != "skeleton.essentials_1000_closure_protocol.v1":
        errors.append("closure: unexpected schema_version")
    evidence=set(protocol.get("evidence_classes",[]))
    required={
        "canonical_contract","implementation_identity","positive_test","negative_test","boundary_test",
        "observability_evidence","security_privacy_isolation_evidence","recovery_rollback_evidence",
        "exact_head_reproduction","independent_verification"
    }
    if not required <= evidence:
        errors.append("closure: required evidence classes missing")
    sig=protocol.get("signatures",{})
    if "distinct identities" not in sig.get("separation_rule",""):
        errors.append("closure: signature separation weakened")
    fresh=protocol.get("freshness",{})
    if not fresh.get("invalidation_triggers"):
        errors.append("closure: freshness invalidation triggers missing")
    if "moves the affected essential out of signed closure" not in fresh.get("revalidation_rule",""):
        errors.append("closure: stale evidence must reopen closure")
    ex=protocol.get("exception_policy",{})
    if ex.get("waivers_can_mark_complete") is not False:
        errors.append("closure: waiver completion forbidden")
    if ex.get("exception_can_bypass_non_compensable_invariant") is not False:
        errors.append("closure: non-compensable bypass forbidden")
    app=protocol.get("applicability",{})
    if app.get("not_applicable_completion") is not False:
        errors.append("closure: not-applicable completion forbidden")
    final=protocol.get("finality",{})
    if final.get("total_required") != 1000:
        errors.append("closure: finality total must be 1000")
    if final.get("no_majority_vote") is not True or final.get("no_score_substitution") is not True:
        errors.append("closure: finality cannot be score/majority based")
    return errors

def validate_ledger(ledger: dict, data: dict) -> list[str]:
    errors: list[str] = []
    if ledger.get("schema_version") != "skeleton.essentials_1000_gap_ledger.v1":
        errors.append("ledger: unexpected schema_version")
    records=ledger.get("records",[])
    if len(records) != 1000:
        errors.append(f"ledger: expected 1000 records, got {len(records)}")
        return errors
    expected=[f"ESS1000-{i:04d}" for i in range(1,1001)]
    if [r.get("essential_id") for r in records] != expected:
        errors.append("ledger: essential identity/order mismatch")
    allowed={"open","specified","implementation_candidate","evidence_incomplete","verification_pending","signed_current","stale","regressed","revoked","blocked"}
    counts={k:0 for k in allowed}
    for i,r in enumerate(records,1):
        state=r.get("state")
        if state not in allowed:
            errors.append(f"ledger: {r.get('essential_id')}: invalid state")
            continue
        counts[state]+=1
        if r.get("paired_psi_layer") != f"PSI1000-{i:04d}":
            errors.append(f"ledger: ESS1000-{i:04d}: PSI pairing mismatch")
        if state=="signed_current":
            if not r.get("implementation_identity"):
                errors.append(f"ledger: ESS1000-{i:04d}: signed without implementation identity")
            if not r.get("closure_receipt_digest"):
                errors.append(f"ledger: ESS1000-{i:04d}: signed without closure receipt")
            if not r.get("current_evidence_ids"):
                errors.append(f"ledger: ESS1000-{i:04d}: signed without evidence")
        else:
            if r.get("closure_receipt_digest") and state=="open":
                errors.append(f"ledger: ESS1000-{i:04d}: open with closure receipt")
    summary=ledger.get("summary",{})
    if summary.get("total") != 1000:
        errors.append("ledger: summary total mismatch")
    for key in ("signed_current","open","stale","regressed","revoked","blocked"):
        if summary.get(key) != counts.get(key,0):
            errors.append(f"ledger: summary {key} mismatch")
    if summary.get("essentials_1000_qualified") is not (counts["signed_current"]==1000):
        errors.append("ledger: qualification mismatch")
    signed_plan=sum(bool(x.get("complete")) for x in data.get("levels",[]))
    if signed_plan != counts["signed_current"]:
        errors.append("ledger: signed-current count diverges from ESS level completion count")
    return errors

def validate(data: dict, scheduler: dict | None = None, closure: dict | None = None, ledger: dict | None = None) -> list[str]:
    errors: list[str] = []
    levels=data.get("levels",[]); strata=data.get("strata",[]); waves=data.get("construction_waves",[])
    rel=data.get("relationship",{}); completion=data.get("completion",{})
    if data.get("schema_version")!="skeleton.essentials_1000.v1": errors.append("unexpected schema_version")
    if len(levels)!=1000: errors.append(f"expected 1000 levels, got {len(levels)}")
    if len(strata)!=100: errors.append(f"expected 100 strata, got {len(strata)}")
    if len(waves)!=100: errors.append(f"expected 100 waves, got {len(waves)}")
    if rel.get("range")!=["ESS1000-0001","ESS1000-1000"]: errors.append("identity range changed")
    if rel.get("expands_top_level_volumes") is not False: errors.append("must not expand top-level volumes")
    if rel.get("frozen_volume_range")!=["VOL-000","VOL-420"]: errors.append("volume freeze changed")
    expected=[f"ESS1000-{i:04d}" for i in range(1,1001)]
    if [x.get("id") for x in levels]!=expected: errors.append("level IDs/order mismatch")
    for i,l in enumerate(levels,1):
        lid=l.get("id")
        if l.get("ordinal")!=i: errors.append(f"{lid}: ordinal mismatch")
        if l.get("stratum_id")!=f"ESS-S{((i-1)//10)+1:03d}": errors.append(f"{lid}: stratum mismatch")
        if l.get("stage")!=((i-1)%10)+1: errors.append(f"{lid}: stage mismatch")
        if l.get("paired_psi_layer")!=f"PSI1000-{i:04d}": errors.append(f"{lid}: PSI pairing mismatch")
        if l.get("mandatory_for_complete_platform") is not True: errors.append(f"{lid}: must be mandatory")
        if l.get("compensable_by_advanced_feature") is not False: errors.append(f"{lid}: essentials cannot be compensable")
        if l.get("documentation_alone_sufficient") is not False: errors.append(f"{lid}: docs alone cannot qualify")
        if l.get("maturity") not in MATURITY: errors.append(f"{lid}: invalid maturity")
        if not l.get("essential_contract") or not l.get("acceptance_proof"): errors.append(f"{lid}: missing contract/proof")
        deps=l.get("depends_on",[])
        for dep in deps:
            if dep not in expected[:i-1]: errors.append(f"{lid}: invalid/forward dependency {dep}")
        stratum=((i-1)//10)+1
        stage=((i-1)%10)+1
        if stratum<100:
            expected_deps=[] if stage==1 else [f"ESS1000-{i-1:04d}"]
        elif stage==1:
            expected_deps=[f"ESS1000-{k*10:04d}" for k in range(1,100)]
        else:
            expected_deps=[f"ESS1000-{i-1:04d}"]
        if deps!=expected_deps:
            errors.append(f"{lid}: dependency topology mismatch")
        if l.get("complete"):
            if l.get("maturity")!="signed_complete": errors.append(f"{lid}: complete without signed_complete")
            if not l.get("implementation_signed"): errors.append(f"{lid}: missing implementation signature")
            if not l.get("independent_verification_signed"): errors.append(f"{lid}: missing independent signature")
            if not l.get("evidence"): errors.append(f"{lid}: missing evidence")
    if completion.get("total_levels")!=1000: errors.append("completion total mismatch")
    signed=sum(bool(x.get("complete")) for x in levels)
    if completion.get("signed_complete")!=signed: errors.append("completion signed count mismatch")
    if completion.get("essentials_1000_qualified") is not (signed==1000): errors.append("qualification mismatch")
    if completion.get("implementation_claim") is not False: errors.append("false implementation claim")
    if levels and levels[-1].get("id")!="ESS1000-1000": errors.append("finality identity mismatch")
    topology=data.get("dependency_topology",{})
    if topology.get("maximum_parallel_domain_lanes")!=99: errors.append("dependency topology: expected 99 parallel lanes")
    if topology.get("finality_fan_in")!=99: errors.append("dependency topology: expected 99-way finality fan-in")
    laws="\n".join(data.get("laws",[]))
    for phrase in ["no advanced feature","Documentation","Stale evidence","PSI-affected domain"]:
        if phrase not in laws: errors.append(f"missing essential law fragment: {phrase}")
    bridge=data.get("psi_priority_bridge",{})
    if bridge.get("mapping")!="ESS1000-nnnn -> PSI1000-nnnn": errors.append("PSI mapping changed")
    if "above optional polish" not in bridge.get("scheduling_rule",""): errors.append("essential priority rule missing")
    if scheduler is not None:
        auth=scheduler.get("authority",{})
        if auth.get("essentials")!="machine/essentials_1000.json": errors.append("scheduler missing ESS-1000 authority")
        ep=scheduler.get("essential_priority",{})
        if ep.get("enabled") is not True: errors.append("scheduler essential priority disabled")
        if ep.get("mapping")!="ESS1000-nnnn -> PSI1000-nnnn": errors.append("scheduler essential mapping mismatch")
        if ep.get("unresolved_essential_priority")!="above_optional_same_domain": errors.append("scheduler essential priority weakened")
    if closure is not None:
        errors.extend(validate_closure_protocol(closure))
    if ledger is not None:
        errors.extend(validate_ledger(ledger,data))
    return errors

def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--path",type=Path,default=PATH)
    p.add_argument("--scheduler-path",type=Path,default=SCHEDULER)
    p.add_argument("--closure-path",type=Path,default=CLOSURE)
    p.add_argument("--ledger-path",type=Path,default=LEDGER)
    a=p.parse_args()
    d=json.loads(a.path.read_text(encoding="utf-8"))
    s=json.loads(a.scheduler_path.read_text(encoding="utf-8"))
    c=json.loads(a.closure_path.read_text(encoding="utf-8"))
    l=json.loads(a.ledger_path.read_text(encoding="utf-8"))
    errors=validate(d,s,c,l)
    if errors:
        for e in errors: print("ERROR:",e)
        return 1
    print("ESS-1000 valid: 1000 essentials / closure freshness + gap ledger + PSI priority enforced")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
