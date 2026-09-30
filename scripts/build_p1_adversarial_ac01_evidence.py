from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

AXIS_ID = "AC-01"
ROOT = Path(__file__).resolve().parents[1]
EXPECTED_MODES = ("clean_machine_e2e","trust_root_rotation","bootstrap_fault_injection","recovery_drill")
REGRESSIONS = {
    "clean_machine_e2e": ("skeleton/testing/test_app_bootstrap.py","test_public_bootstrap_is_dependency_closed_and_sanitized"),
    "trust_root_rotation": ("skeleton/testing/test_shell_ai_runtime_trust.py","test_runtime_trust_signature_metadata_scope_is_verified"),
    "bootstrap_fault_injection": ("skeleton/testing/test_shell_ai_runtime_trust.py","test_runtime_trust_guard_wrong_expected_epoch_fails_closed"),
    "recovery_drill": ("skeleton/testing/test_state_recovery_drill.py","test_recovery_journal_requires_authority_verification_before_rebuild"),
}
IMPLEMENTATIONS = ("skeleton/bootstrap/genesis.py","skeleton/shells/ai/runtime_trust_store.py","frontend/app/safe-mode.tsx")
OWNER_ID = "ACC-P1-EVID-04"

class AC01EvidenceError(ValueError): pass

def _sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()

def build_ac01_evidence(root: Path, *, expected_head: str) -> dict:
    if len(expected_head) != 40 or expected_head != expected_head.lower() or any(c not in "0123456789abcdef" for c in expected_head):
        raise AC01EvidenceError("expected_head must be lowercase 40-character git SHA")
    closure = json.loads((root/"machine/ai_adversarial_closure.json").read_text())
    axis = next(x for x in closure["closure_axes"] if x["id"] == AXIS_ID)
    if tuple(axis["required_evidence_modes"]) != EXPECTED_MODES:
        raise AC01EvidenceError("AC-01 mode contract drift")
    impl = [{"path": p, "sha256": _sha(root/p)} for p in IMPLEMENTATIONS]
    evidence, proofs = [], {}
    for mode, (rel, token) in REGRESSIONS.items():
        p = root/rel
        text = p.read_text(encoding="utf-8")
        if token not in text: raise AC01EvidenceError(f"missing regression token: {token}")
        digest = hashlib.sha256(json.dumps({"axis_id":AXIS_ID,"mode":mode,"head":expected_head,"impl":impl,"regression":[rel,token,_sha(p)]},sort_keys=True,separators=(",",":")).encode()).hexdigest()
        proofs[mode] = {"axis_id":AXIS_ID,"mode":mode,"expected_head":expected_head,"implementation":impl,"regression":{"path":rel,"required_tokens":[token],"sha256":_sha(p)},"proof_digest":digest}
        evidence.append({"category":mode,"digest":digest,"source":f"p1:adversarial-ac01-evidence:{AXIS_ID}:{mode}:{expected_head}"})
    candidate = {"axis_id":AXIS_ID,"owner_id":OWNER_ID,"statement":axis["gap"],"required_evidence_modes":list(EXPECTED_MODES),"expected_head":expected_head,"evidence":evidence,"proofs":proofs,"recommended_severity":"high","recommended_disposition":"evidence","creates_binding":False,"accepts_risk":False,"lowers_severity":False,"promotes_maturity":False}
    return {"axis_id":AXIS_ID,"candidate_count":1,"required_evidence_mode_count":4,"candidate_binding_count":0,"non_authoritative":True,"creates_bindings":False,"accepts_risk":False,"lowers_severity":False,"promotes_maturity":False,"candidate":candidate}

if __name__ == "__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--expected-head",required=True); parser.add_argument("--out",required=True); args=parser.parse_args()
    report=build_ac01_evidence(ROOT,expected_head=args.expected_head)
    Path(args.out).write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"axis_id":AXIS_ID,"modes":EXPECTED_MODES},sort_keys=True))
