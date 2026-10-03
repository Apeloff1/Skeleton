"""Convert verified CI failure evidence into bounded canonical repair proposals."""
from __future__ import annotations
import hashlib,json
from dataclasses import dataclass,asdict
from .ci_failure_attribution import attribute
@dataclass(frozen=True)
class RepairWork:
 id:str; gate:str; category:str; objective:str; validation:tuple[str,...]; source_run_id:int
def derive(gate:str,run_id:int,head_sha:str)->RepairWork:
 a=attribute(gate)
 identity=hashlib.sha256(f"{head_sha}:{run_id}:{gate}".encode()).hexdigest()[:20]
 return RepairWork("ci-"+identity,gate,a.category,f"Repair reproducible exact-head failure in {gate} without weakening the gate.",(gate,),run_id)
