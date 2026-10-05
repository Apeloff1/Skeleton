from dataclasses import dataclass
@dataclass(frozen=True)
class ResearchBranchPolicy: prefix:str; owner:str; production_gates:tuple[str,...]
@dataclass(frozen=True)
class ResearchBranch: name:str; parent_sha:str; experiment_id:str; owner:str
@dataclass(frozen=True)
class ResearchMergeCandidate: branch:ResearchBranch; evidence_ids:tuple[str,...]; passed_gates:frozenset[str]
def promote(c,p):
 if not c.branch.name.startswith(p.prefix) or c.branch.owner!=p.owner:raise PermissionError("research branch ownership policy")
 if not set(p.production_gates).issubset(c.passed_gates):raise PermissionError("production gates not satisfied")
 if not c.evidence_ids:raise PermissionError("promotion evidence required")
 return True
