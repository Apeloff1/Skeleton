"""Map real crawler events to deterministic baby-dragon visual states."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class DragonVisualState:
 pose:str;effect:str;label:str;progress:float
_MAP={
 "frontier_discovered":("perch","spark","Discovered",.05),
 "dragon_travel":("fly","trail","Travelling",.12),
 "visual_probe":("sniff","scan","Looking",.20),
 "robots_check":("listen","rune","Checking rules",.28),
 "fetch_started":("pounce","wind","Acquiring",.38),
 "fetch_received":("hold","glow","Payload received",.50),
 "policy_rejected":("turn_away","fizzle","Rejected",1.),
 "acquisition_accepted":("charge","embers","Acquisition accepted",.62),
 "burn_started":("breath","fire","Burning into knowledge",.72),
 "burn_chunk":("breath","ember_stream","Extracting chunks",.85),
 "burn_complete":("proud","ash_to_stars","Extraction complete",1.),
 "retry_wait":("curl","smoke","Waiting politely",.25),
 "crawl_complete":("sleep","warm_embers","Crawl complete",1.),
}
def visual_state(event):
 pose,effect,label,progress=_MAP[event.kind]
 return DragonVisualState(pose,effect,label,progress)
