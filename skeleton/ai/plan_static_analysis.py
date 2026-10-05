from dataclasses import dataclass
@dataclass(frozen=True)
class PlanLintRule: rule_id:str; severity:str
@dataclass(frozen=True)
class PlanDiagnostic: rule_id:str; location:str; severity:str; remediation:str
@dataclass(frozen=True)
class PlanAnalysis: ir_version:str; diagnostics:tuple[PlanDiagnostic,...]
def analyze(ir_version,steps,rules):
 out=[]
 ids=set()
 for i,s in enumerate(steps):
  if s["id"] in ids:out.append(PlanDiagnostic("duplicate-step",str(i),"error","use unique step id"))
  ids.add(s["id"])
  if s.get("privileged") and not s.get("authority"):out.append(PlanDiagnostic("missing-authority",str(i),"error","declare authority"))
 return PlanAnalysis(ir_version,tuple(out))
