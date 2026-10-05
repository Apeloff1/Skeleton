"""Cognitive strategy, plan analysis and tool composition VOL-366..373."""
from dataclasses import dataclass
from enum import Enum
@dataclass(frozen=True,slots=True)
class StrategyVersion: name:str; version:str
@dataclass(frozen=True,slots=True)
class StrategyEvidence: benchmark_id:str; eval_passed:bool; cost:float
@dataclass(frozen=True,slots=True)
class CognitiveStrategy: identity:StrategyVersion; evidence:tuple[StrategyEvidence,...]; production:bool=False
def production_eligible(s):return bool(s.identity.name) and bool(s.identity.version) and bool(s.evidence) and all(bool(e.benchmark_id) and e.eval_passed and e.cost>=0 for e in s.evidence)
@dataclass(frozen=True,slots=True)
class StrategyConstraint: allowed:frozenset[StrategyVersion]; max_cost:float
@dataclass(frozen=True,slots=True)
class StrategySelection: candidates:tuple[CognitiveStrategy,...]; constraint:StrategyConstraint
@dataclass(frozen=True,slots=True)
class StrategyDecision: selected:StrategyVersion|None; abstained:bool; reason:str
def select_strategy(x):
 if x.constraint.max_cost<0:raise ValueError("strategy cost bound must be nonnegative")
 ok=[s for s in x.candidates if s.identity in x.constraint.allowed and production_eligible(s) and sum(e.cost for e in s.evidence)<=x.constraint.max_cost]
 if not ok:return StrategyDecision(None,True,"no admissible strategy")
 s=min(ok,key=lambda z:(sum(e.cost for e in z.evidence),z.identity.name,z.identity.version));return StrategyDecision(s.identity,False,"admissible")
class ReasoningStage(str,Enum): PLAN="plan"; VERIFY="verify"; EXECUTE="execute"
@dataclass(frozen=True,slots=True)
class ReasoningCost: operation_id:str; strategy:StrategyVersion; model:str; model_version:str; stage:ReasoningStage; units:float
@dataclass(frozen=True,slots=True)
class CostAttribution: operation_id:str; total_units:float; records:int
def attribute_cost(xs):
 if not xs:return CostAttribution("",0,0)
 op=xs[0].operation_id
 if not op or any(not x.strategy.name or not x.strategy.version or not x.model or not x.model_version or x.units<0 for x in xs):raise ValueError("invalid reasoning cost identity")
 if any(x.operation_id!=op for x in xs):raise ValueError("mixed operations")
 return CostAttribution(op,sum(x.units for x in xs),len(xs))
class Severity(str,Enum): INFO="info"; WARNING="warning"; ERROR="error"
@dataclass(frozen=True,slots=True)
class PlanLintRule: rule_id:str; version:str
@dataclass(frozen=True,slots=True)
class PlanDiagnostic: rule_id:str; location:str; severity:Severity; remediation:str
@dataclass(frozen=True,slots=True)
class PlanAnalysis: ir_version:str; diagnostics:tuple[PlanDiagnostic,...]
def analyze_plan(ir_version,nodes,edges,rules):
 if not ir_version or not nodes:raise ValueError("plan identity and nodes required")
 if any(not r.rule_id or not r.version for r in rules):raise ValueError("lint rule identity required")
 if len({(r.rule_id,r.version) for r in rules})!=len(rules):raise ValueError("duplicate lint rule")
 ids=set(nodes);d=[]
 for a,b in edges:
  if a not in ids or b not in ids:d.append(PlanDiagnostic("edge-endpoint","edges",Severity.ERROR,"declare both endpoints"))
 if len(ids)!=len(nodes):d.append(PlanDiagnostic("duplicate-node","nodes",Severity.ERROR,"use unique node ids"))
 graph={n:[] for n in ids}
 for a,b in edges:
  if a in ids and b in ids:graph[a].append(b)
 visiting=set();visited=set()
 def visit(n):
  if n in visiting:return True
  if n in visited:return False
  visiting.add(n)
  if any(visit(x) for x in graph[n]):return True
  visiting.remove(n);visited.add(n);return False
 if any(visit(n) for n in sorted(ids) if n not in visited):d.append(PlanDiagnostic("cycle","edges",Severity.ERROR,"remove dependency cycle"))
 return PlanAnalysis(ir_version,tuple(sorted(d,key=lambda x:(x.location,x.rule_id))))
@dataclass(frozen=True,slots=True)
class SimulatedStep: step_id:str; scenario:str; outcome:str
@dataclass(frozen=True,slots=True)
class SimulationFinding: scenario:str; risk:str
@dataclass(frozen=True,slots=True)
class PlanSimulation: steps:tuple[SimulatedStep,...]; findings:tuple[SimulationFinding,...]
    @property
    def production_evidence(self):return False
def simulate_plan(step_ids):
 if not step_ids or any(not s for s in step_ids) or len(set(step_ids))!=len(step_ids):raise ValueError("unique simulation steps required")
 scenarios=("success","failure","timeout","resource_exhaustion")
 steps=tuple(SimulatedStep(s,x,"simulated") for s in step_ids for x in scenarios)
 findings=tuple(SimulationFinding(x,"simulated adverse outcome") for x in scenarios if x!="success")
 return PlanSimulation(steps,findings)
@dataclass(frozen=True,slots=True)
class ToolBinding: tool_id:str; version:str; authority:frozenset[str]; input_schema:str; output_schema:str; trust_class:str
@dataclass(frozen=True,slots=True)
class ToolComposition: bindings:tuple[ToolBinding,...]; requested_authority:frozenset[str]
@dataclass(frozen=True,slots=True)
class CompositionResult: admissible:bool; effective_authority:frozenset[str]; reason:str
def compose_tools(c):
 if not c.bindings:return CompositionResult(False,frozenset(),"no tools")
 if any(not b.tool_id or not b.version or not b.input_schema or not b.output_schema or not b.trust_class for b in c.bindings):return CompositionResult(False,frozenset(),"incomplete tool identity")
 if len({(b.tool_id,b.version) for b in c.bindings})!=len(c.bindings):return CompositionResult(False,frozenset(),"duplicate tool binding")
 common=set(c.bindings[0].authority)
 for b in c.bindings[1:]:common&=b.authority
 effective=frozenset(common)&c.requested_authority
 if effective!=c.requested_authority:return CompositionResult(False,effective,"authority not shared by every tool")
 if any(a.output_schema!=b.input_schema or a.trust_class!=b.trust_class for a,b in zip(c.bindings,c.bindings[1:])):return CompositionResult(False,effective,"schema/trust mismatch")
 return CompositionResult(True,effective,"compatible")
