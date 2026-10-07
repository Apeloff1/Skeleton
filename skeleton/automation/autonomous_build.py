"""Evidence-driven controller for repeated autonomous build cycles."""
from __future__ import annotations
import hashlib,json,os,tempfile
from dataclasses import dataclass,asdict,field
from pathlib import Path
from typing import Any,Mapping
from .studio_convergence import evaluate
from .studio_promotion import PromotionEvidence,promotable
from .build_state_store import advance as advance_state_envelope
from .build_lease import acquire as acquire_build_lease

SCHEMA="autonomous-studio.build-controller.v1"
TERMINAL={"complete","quarantined","exhausted"}

@dataclass
class BuildState:
 schema:str=SCHEMA; build_id:str=""; cycle:int=0; status:str="active"; accepted:int=0; failures:int=0
 last_generation:str=""; last_progress:str=""; stagnant:int=0; terminal_reason:str=""
 outcomes:list[str]=field(default_factory=list); state_sha256:str=""
 @classmethod
 def load(cls,path:Path):
  if not path.exists(): return cls()
  if path.is_symlink() or path.stat().st_size>512_000: raise ValueError("unsafe build state")
  raw=json.loads(path.read_text()); claimed=raw.get("state_sha256",""); raw["state_sha256"]=""
  actual=hashlib.sha256(json.dumps(raw,sort_keys=True,separators=(",",":")).encode()).hexdigest()
  if claimed!=actual: raise ValueError("build state integrity mismatch")
  raw["state_sha256"]=claimed; return cls(**raw)
 def dump(self,path:Path):
  self.state_sha256=""; raw=asdict(self)
  self.state_sha256=hashlib.sha256(json.dumps(raw,sort_keys=True,separators=(",",":")).encode()).hexdigest()
  raw["state_sha256"]=self.state_sha256; path.parent.mkdir(parents=True,exist_ok=True)
  fd,name=tempfile.mkstemp(dir=path.parent,prefix="."+path.name+".",suffix=".tmp")
  try:
   with os.fdopen(fd,"w") as h: json.dump(raw,h,sort_keys=True,indent=2); h.write("\n"); h.flush(); os.fsync(h.fileno())
   os.replace(name,path)
  except BaseException:
   Path(name).unlink(missing_ok=True); raise

def build_identity(supervisor:Mapping[str,Any])->str:
 return hashlib.sha256(f"{supervisor.get('team')}:{supervisor.get('issue_number')}".encode()).hexdigest()[:24]

def advance(state:BuildState,*,supervisor:Mapping[str,Any],validated:bool,outcome_sha:str="",max_cycles:int=80,max_failures:int=8,max_stagnant:int=5)->BuildState:
 if state.status in TERMINAL:return state
 identity=build_identity(supervisor)
 if state.build_id and state.build_id!=identity: state=BuildState(build_id=identity)
 if not state.build_id: state.build_id=identity
 progress=supervisor.get("progress",{}); fingerprint=str(progress.get("fingerprint_sha256",""))
 generation=str(supervisor.get("generation_id",""))
 if len(fingerprint)!=64: raise ValueError("missing canonical progress fingerprint")
 state.cycle+=1
 if fingerprint==state.last_progress and state.cycle>1: state.stagnant+=1
 else: state.stagnant=0
 state.last_progress=fingerprint; state.last_generation=generation
 if validated:
  state.accepted+=1
  if outcome_sha: state.outcomes=(state.outcomes+[outcome_sha])[-128:]
 else: state.failures+=1
 counts=progress.get("counts",{}) if isinstance(progress,Mapping) else {}
 queued=int(counts.get("queued",0)); blocked=int(counts.get("blocked",0))
 health=evaluate(queued=queued,blocked=blocked,active_lanes=1 if queued else 0,quarantined_lanes=0)
 if bool(progress.get("terminal")) or health.status=="complete": state.status="complete"; state.terminal_reason="canonical_queue_drained"
 elif state.failures>=max_failures: state.status="quarantined"; state.terminal_reason="failure_budget"
 elif state.stagnant>=max_stagnant: state.status="quarantined"; state.terminal_reason="stagnation"
 elif state.cycle>=max_cycles: state.status="exhausted"; state.terminal_reason="cycle_budget"
 else: state.status="continue"
 return state

def should_continue(state:BuildState)->bool:return state.status=="continue"

def main(argv=None)->int:
 import argparse
 p=argparse.ArgumentParser()
 p.add_argument("--state",required=True); p.add_argument("--repo-state",required=True)
 p.add_argument("--validated",action="store_true"); p.add_argument("--outcome-sha",default="")
 p.add_argument("--max-cycles",type=int,default=80); p.add_argument("--max-failures",type=int,default=8); p.add_argument("--max-stagnant",type=int,default=5)
 p.add_argument("--durable-envelope",default=""); p.add_argument("--lease-owner",default=""); p.add_argument("--expected-lease-epoch",type=int,default=0)
 a=p.parse_args(argv); state=BuildState.load(Path(a.state))
 repo=json.loads(Path(a.repo_state).read_text()); supervisor=repo.get("_shift_supervisor")
 if not isinstance(supervisor,Mapping): raise ValueError("missing supervisor state")
 state=advance(state,supervisor=supervisor,validated=a.validated,outcome_sha=a.outcome_sha,max_cycles=a.max_cycles,max_failures=a.max_failures,max_stagnant=a.max_stagnant)
 state.dump(Path(a.state))
 if a.durable_envelope:
  head=os.environ.get("GITHUB_SHA","")
  if len(head)!=40: raise ValueError("durable build state requires exact GITHUB_SHA")
  lease=acquire_build_lease(None,owner=a.lease_owner or os.environ.get("GITHUB_RUN_ID","local"),expected_epoch=a.expected_lease_epoch,head_sha=head)
  envelope=advance_state_envelope(None,head_sha=head,payload={"build":asdict(state),"lease":asdict(lease)})
  Path(a.durable_envelope).write_text(json.dumps({"revision":envelope.revision,"head_sha":envelope.head_sha,"payload":envelope.payload,"sha256":envelope.sha256},sort_keys=True,indent=2)+"\n",encoding="utf-8")
 print(json.dumps(asdict(state),sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
