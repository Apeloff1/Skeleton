#!/usr/bin/env python3
from __future__ import annotations

import argparse, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "machine" / "essentials_1000.json"
SCHEDULER = ROOT / "machine" / "project_self_improvement_idle_scheduler.json"

MATURITY = ["planned","specified","implemented","integrated","independently_verified","signed_complete"]

def validate(data: dict, scheduler: dict | None = None) -> list[str]:
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
        for dep in l.get("depends_on",[]):
            if dep not in expected[:i-1]: errors.append(f"{lid}: invalid/forward dependency {dep}")
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
    laws="\n".join(data.get("laws",[]))
    for phrase in ["no advanced feature","Documentation","Stale evidence","PSI-affected domain"]:
        if phrase not in laws: errors.append(f"missing essential law fragment: {phrase}")
    bridge=data.get("psi_priority_bridge",{})
    if bridge.get("mapping")!="ESS1000-nnnn -> PSI1000-nnnn": errors.append("PSI mapping changed")
    if "outrank optional polish" not in bridge.get("scheduling_rule",""): errors.append("essential priority rule missing")
    if scheduler is not None:
        auth=scheduler.get("authority",{})
        if auth.get("essentials")!="machine/essentials_1000.json": errors.append("scheduler missing ESS-1000 authority")
        ep=scheduler.get("essential_priority",{})
        if ep.get("enabled") is not True: errors.append("scheduler essential priority disabled")
        if ep.get("mapping")!="ESS1000-nnnn -> PSI1000-nnnn": errors.append("scheduler essential mapping mismatch")
        if ep.get("unresolved_essential_priority")!="above_optional_same_domain": errors.append("scheduler essential priority weakened")
    return errors

def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--path",type=Path,default=PATH)
    p.add_argument("--scheduler-path",type=Path,default=SCHEDULER)
    a=p.parse_args()
    d=json.loads(a.path.read_text(encoding="utf-8"))
    s=json.loads(a.scheduler_path.read_text(encoding="utf-8"))
    errors=validate(d,s)
    if errors:
        for e in errors: print("ERROR:",e)
        return 1
    print("ESS-1000 valid: 1000 non-compensable essentials / 100 strata / PSI priority bridge enforced")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
