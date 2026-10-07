from dataclasses import dataclass
@dataclass(frozen=True)
class ResearchBranchPolicy: prefix:str; owner:str; production_gates:tuple[str,...]
@dataclass(frozen=True)
class ResearchBranch: name:str; parent_sha:str; experiment_id:str; owner:str
@dataclass(frozen=True)
class ResearchMergeCandidate: branch:ResearchBranch; evidence_ids:tuple[str,...]; passed_gates:frozenset[str]
def promote(c,p):
 if not all((p.prefix,p.owner,c.branch.name,c.branch.parent_sha,c.branch.experiment_id,c.branch.owner)) or len(p.production_gates)!=len(set(p.production_gates)) or any(not g for g in p.production_gates):raise ValueError("valid branch promotion policy required")
 if len(c.evidence_ids)!=len(set(c.evidence_ids)) or any(not e for e in c.evidence_ids):raise ValueError("unique promotion evidence required")
 if not c.branch.name.startswith(p.prefix) or c.branch.owner!=p.owner:raise PermissionError("research branch ownership policy")
 if not set(p.production_gates).issubset(c.passed_gates):raise PermissionError("production gates not satisfied")
 if not c.evidence_ids:raise PermissionError("promotion evidence required")
 return True
