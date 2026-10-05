from dataclasses import dataclass,field
@dataclass(frozen=True)
class SimulatedStep: step_id:str; scenario:str; outcome:str
@dataclass(frozen=True)
class SimulationFinding: step_id:str; severity:str; message:str
@dataclass(frozen=True)
class PlanSimulation:
 steps:tuple[SimulatedStep,...]; findings:tuple[SimulationFinding,...]; production_evidence:bool=field(default=False,init=False)
def simulate(step_ids,scenarios):
 step_ids=tuple(step_ids);scenarios=tuple(scenarios)
 if not step_ids or len(step_ids)!=len(set(step_ids)) or any(not isinstance(x,str) or not x for x in step_ids):raise ValueError("unique simulation step identities required")
 if not scenarios:raise ValueError("simulation scenarios required")
 allowed={"success","failure","timeout","resource"};steps=[];findings=[]
 for sid in step_ids:
  for scenario in scenarios:
   if scenario not in allowed:outcome="failed";findings.append(SimulationFinding(sid,"error","unknown-scenario:"+str(scenario)))
   else:
    outcome="failed" if scenario!="success" else "success"
    if outcome!="success":findings.append(SimulationFinding(sid,"warning",scenario))
   steps.append(SimulatedStep(sid,scenario,outcome))
 return PlanSimulation(tuple(steps),tuple(findings))
