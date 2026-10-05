from dataclasses import dataclass
@dataclass(frozen=True)
class PlanLintRule: rule_id:str; severity:str
@dataclass(frozen=True)
class PlanDiagnostic: rule_id:str; location:str; severity:str; remediation:str
@dataclass(frozen=True)
class PlanAnalysis: ir_version:str; diagnostics:tuple[PlanDiagnostic,...]
def analyze(ir_version,steps,rules):
 if not ir_version:raise ValueError("IR version required")
 rules=tuple(rules)
 if any(not r.rule_id or r.severity not in {"info","warning","error"} for r in rules):raise ValueError("valid lint rules required")
 rule_map={r.rule_id:r for r in rules}
 if len(rule_map)!=len(rules):raise ValueError("duplicate lint rule")
 out=[];ids=set()
 for i,s in enumerate(steps):
  if not isinstance(s,dict) or not isinstance(s.get("id"),str) or not s["id"]:
   out.append(PlanDiagnostic("malformed-step",str(i),"error","declare step id"));continue
  if s["id"] in ids:out.append(PlanDiagnostic("duplicate-step",str(i),rule_map.get("duplicate-step",PlanLintRule("", "error")).severity,"use unique step id"))
  ids.add(s["id"])
  if s.get("privileged") and not s.get("authority"):out.append(PlanDiagnostic("missing-authority",str(i),rule_map.get("missing-authority",PlanLintRule("", "error")).severity,"declare authority"))
 return PlanAnalysis(ir_version,tuple(out))
