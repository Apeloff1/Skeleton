from dataclasses import dataclass
@dataclass(frozen=True)
class SimulatedStep: step_id:str; scenario:str; outcome:str
@dataclass(frozen=True)
class SimulationFinding: step_id:str; severity:str; message:str
@dataclass(frozen=True)
class PlanSimulation: steps:tuple[SimulatedStep,...]; findings:tuple[SimulationFinding,...]; production_evidence:bool=False
def simulate(step_ids,scenarios):
 steps=[];findings=[]
 for sid in step_ids:
  for scenario in scenarios:
   outcome="failed" if scenario in {"failure","timeout","resource"} else "success";steps.append(SimulatedStep(sid,scenario,outcome))
   if outcome!="success":findings.append(SimulationFinding(sid,"warning",scenario))
 return PlanSimulation(tuple(steps),tuple(findings))
