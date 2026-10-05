from dataclasses import dataclass
@dataclass(frozen=True)
class ResearchComputeJob: job_id:str; priority:int; quota:int; provenance:str
@dataclass(frozen=True)
class ResearchAllocation: job_id:str; units:int
@dataclass(frozen=True)
class ResearchQueue:
 jobs:tuple[ResearchComputeJob,...]
 def allocate(self,capacity,production_reserved):
  if any(isinstance(x,bool) or not isinstance(x,int) or x<0 for x in (capacity,production_reserved)) or production_reserved>capacity:raise ValueError("valid compute capacity required")
  ids=[j.job_id for j in self.jobs]
  if len(ids)!=len(set(ids)) or any(not j.job_id or not j.provenance or isinstance(j.priority,bool) or not isinstance(j.priority,int) or isinstance(j.quota,bool) or not isinstance(j.quota,int) or j.quota<=0 for j in self.jobs):raise ValueError("valid unique research jobs required")
  free=max(0,capacity-production_reserved);out=[]
  for j in sorted(self.jobs,key=lambda x:(-x.priority,x.job_id)):
   n=min(j.quota,free)
   if n:out.append(ResearchAllocation(j.job_id,n));free-=n
  return tuple(out)
