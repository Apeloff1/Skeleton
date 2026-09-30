#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, re, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SHA40 = re.compile(r"^[0-9a-f]{40}$")
AXIS_ID = "AC-02"
EXPECTED_MODES = ("shutdown_race","restart_replay","fault_injection","state_machine_property")
TESTS = ("skeleton/testing/test_adversarial_ac02_lifecycle.py","skeleton/testing/test_state_recovery_drill.py","skeleton/testing/test_shell_ai_runtime_trust.py")
OWNER_ID = "ACC-P1-EVID-04"
class AC02EvidenceError(RuntimeError): pass
def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
def run_tests() -> dict:
    p=subprocess.run([sys.executable,"-m","pytest","-q","--noconftest",*TESTS],cwd=ROOT,text=True,capture_output=True)
    receipt={"returncode":p.returncode,"stdout_digest":hashlib.sha256(p.stdout.encode()).hexdigest(),"stderr_digest":hashlib.sha256(p.stderr.encode()).hexdigest(),"tests":TESTS}
    if p.returncode: raise AC02EvidenceError(p.stderr[-800:] or "AC-02 regressions failed")
    return receipt
def build(expected_head: str) -> dict:
    if not SHA40.fullmatch(expected_head): raise AC02EvidenceError("expected_head must be lowercase 40-character git SHA")
    closure=json.loads((ROOT/"machine/ai_adversarial_closure.json").read_text())
    axis=next((a for a in closure["closure_axes"] if a["id"]==AXIS_ID),None)
    if axis is None or tuple(axis["required_evidence_modes"]) != EXPECTED_MODES: raise AC02EvidenceError("AC-02 evidence mode drift")
    receipt=run_tests(); proofs={}
    oracles={"shutdown_race":"shutdown fences new work and drains accepted work exactly once","restart_replay":"restart requires a stopped state and does not replay committed effects","fault_injection":"wrong trust epoch remains fail-closed during lifecycle regression","state_machine_property":"running -> draining -> stopped -> running is the only restart path"}
    for mode in EXPECTED_MODES:
        proof={"axis_id":AXIS_ID,"mode":mode,"expected_head":expected_head,"oracle":oracles[mode],"test_receipt":receipt}
        proof["proof_digest"]=digest(proof); proofs[mode]=proof
    evidence=[{"source":f"p1:adversarial-ac02-evidence:{AXIS_ID}:{m}:{expected_head}","digest":proofs[m]["proof_digest"],"category":m} for m in EXPECTED_MODES]
    candidate={"axis_id":AXIS_ID,"axis_name":axis["name"],"expected_head":expected_head,"required_evidence_modes":list(EXPECTED_MODES),"owner_id":OWNER_ID,"recommended_severity":"high","recommended_disposition":"evidence","evidence":evidence,"proofs":proofs,"non_authoritative":True,"creates_binding":False,"accepts_risk":False,"lowers_severity":False,"promotes_maturity":False}
    candidate["candidate_digest"]=digest(candidate)
    return {"schema_version":1,"engine":"p1-adversarial-ac02-evidence-v1","axis_id":AXIS_ID,"expected_head":expected_head,"candidate_count":1,"required_evidence_mode_count":4,"non_authoritative":True,"creates_bindings":False,"accepts_risk":False,"lowers_severity":False,"promotes_maturity":False,"candidate":candidate,"report_digest":digest(candidate)}
def main()->int:
    p=argparse.ArgumentParser(); p.add_argument("--expected-head",required=True); p.add_argument("--out",type=Path); a=p.parse_args()
    try: report=build(a.expected_head)
    except AC02EvidenceError as exc: print(f"P1 AC-02 evidence: rejected: {exc}",file=sys.stderr); return 2
    if a.out: a.out.parent.mkdir(parents=True,exist_ok=True); a.out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("P1 AC-02 evidence: OK (1 candidate, 4 lifecycle modes)"); return 0
if __name__=="__main__": raise SystemExit(main())
