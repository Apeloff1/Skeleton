from __future__ import annotations
import argparse,hashlib,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; SHA40=re.compile(r"^[0-9a-f]{40}$")
AXIS_ID="AC-03"; EXPECTED_MODES=("resource_exhaustion","load_test","soak","degraded_mode")
TESTS=("skeleton/testing/test_adversarial_ac03_exhaustion.py","skeleton/testing/test_state_recovery_drill.py")
class AC03EvidenceError(RuntimeError): pass
def digest(v): return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
def build(head):
    if not SHA40.fullmatch(head): raise AC03EvidenceError("expected_head must be lowercase 40-character git SHA")
    closure=json.loads((ROOT/"machine/ai_adversarial_closure.json").read_text())
    axis=next((a for a in closure["closure_axes"] if a["id"]==AXIS_ID),None)
    if axis is None or tuple(axis["required_evidence_modes"])!=EXPECTED_MODES: raise AC03EvidenceError("AC-03 evidence mode drift")
    p=subprocess.run([sys.executable,"-m","pytest","-q","--noconftest",*TESTS],cwd=ROOT,text=True,capture_output=True)
    if p.returncode: raise AC03EvidenceError(p.stderr[-800:] or "AC-03 regressions failed")
    receipt={"returncode":p.returncode,"stdout_digest":hashlib.sha256(p.stdout.encode()).hexdigest(),"stderr_digest":hashlib.sha256(p.stderr.encode()).hexdigest(),"tests":TESTS}
    oracles={"resource_exhaustion":"hard budget exhaustion fails closed without overcommit","load_test":"repeated admission remains bounded by configured budget","soak":"repeated release/reacquire preserves invariant","degraded_mode":"degraded operation cannot bypass budget"}
    proofs={}
    for mode in EXPECTED_MODES:
        q={"axis_id":AXIS_ID,"mode":mode,"expected_head":head,"oracle":oracles[mode],"test_receipt":receipt}; q["proof_digest"]=digest(q); proofs[mode]=q
    evidence=[{"source":f"p1:adversarial-ac03-evidence:{AXIS_ID}:{m}:{head}","digest":proofs[m]["proof_digest"],"category":m} for m in EXPECTED_MODES]
    candidate={"axis_id":AXIS_ID,"axis_name":axis["name"],"expected_head":head,"required_evidence_modes":list(EXPECTED_MODES),"recommended_severity":"high","recommended_disposition":"evidence","evidence":evidence,"proofs":proofs,"non_authoritative":True,"creates_binding":False,"accepts_risk":False,"lowers_severity":False,"promotes_maturity":False}
    candidate["candidate_digest"]=digest(candidate)
    return {"schema_version":1,"engine":"p1-adversarial-ac03-evidence-v1","axis_id":AXIS_ID,"expected_head":head,"candidate_count":1,"required_evidence_mode_count":4,"non_authoritative":True,"creates_bindings":False,"accepts_risk":False,"lowers_severity":False,"promotes_maturity":False,"candidate":candidate,"report_digest":digest(candidate)}
def main():
    p=argparse.ArgumentParser();p.add_argument("--expected-head",required=True);p.add_argument("--out",type=Path);a=p.parse_args()
    try:r=build(a.expected_head)
    except AC03EvidenceError as e: print(f"P1 AC-03 evidence: rejected: {e}",file=sys.stderr);return 2
    if a.out:a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n")
    print("P1 AC-03 evidence: OK (1 candidate, 4 exhaustion modes)");return 0
if __name__=="__main__":raise SystemExit(main())
