from dataclasses import dataclass
@dataclass(frozen=True)
class KnowledgeConflict:
 claim_ids:tuple[str,...]; evidence_ids:tuple[str,...]
 def __post_init__(self):
  if len(self.claim_ids)<2 or len(set(self.claim_ids))!=len(self.claim_ids):raise ValueError("conflict requires distinct competing claims")
@dataclass(frozen=True)
class ReconciliationCase: case_id:str; conflict:KnowledgeConflict
@dataclass(frozen=True)
class ReconciliationDecision: case_id:str; outcome:str; selected_claim:str|None; competing_evidence:tuple[str,...]; rule:str
def reconcile(case,rule,selected=None):
 if rule not in {"verified-supersession","scope-qualified","unresolved"}:raise ValueError("unjustified reconciliation rule")
 if rule=="unresolved" and selected is not None:raise ValueError("unresolved conflict cannot select winner")
 if rule!="unresolved" and selected not in case.conflict.claim_ids:raise ValueError("selected claim absent from conflict")
 if rule=="verified-supersession" and not case.conflict.evidence_ids:raise PermissionError("verified supersession requires evidence")
 return ReconciliationDecision(case.case_id,rule,selected,case.conflict.evidence_ids,rule)
