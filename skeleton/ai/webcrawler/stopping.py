"""Calibrated stop/continue policy for autonomous research."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class ResearchStopDecision:
 action:str;score:float;independent_clusters:int;uncertainty:float;max_influence:float;reasons:tuple[str,...]
def decide_research_stop(*,assurance,uncertainty,max_influence,min_score=.7,min_clusters=3,max_uncertainty=.2,max_single_source_influence=.2):
 reasons=[]
 if float(assurance["score"])<min_score:reasons.append("low-assurance")
 if int(assurance["independent_evidence_clusters"])<min_clusters:reasons.append("insufficient-independent-evidence")
 if uncertainty>max_uncertainty:reasons.append("high-uncertainty")
 if max_influence>max_single_source_influence:reasons.append("single-source-brittleness")
 return ResearchStopDecision("continue" if reasons else "stop",float(assurance["score"]),int(assurance["independent_evidence_clusters"]),float(uncertainty),float(max_influence),tuple(reasons))
