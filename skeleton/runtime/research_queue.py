from dataclasses import dataclass
@dataclass(frozen=True)
class ResearchComputeJob: job_id:str; priority:int; quota:int; provenance:str
@dataclass(frozen=True)
class ResearchAllocation: job_id:str; units:int
@dataclass(frozen=True)
class ResearchQueue:
 jobs:tuple[ResearchComputeJob,...]
 def allocate(self,capacity,production_reserved):
  free=max(0,capacity-production_reserved);out=[]
  for j in sorted(self.jobs,key=lambda x:(-x.priority,x.job_id)):
   n=min(j.quota,free)
   if n:out.append(ResearchAllocation(j.job_id,n));free-=n
  return tuple(out)
