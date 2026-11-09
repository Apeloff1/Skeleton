"""Non-authoritative scheduling simulation for VOL-316."""
from dataclasses import dataclass
import math
@dataclass(frozen=True)
class WorkloadTrace:
 durations:tuple[float,...]; assumptions:tuple[str,...]
 def __post_init__(self):
  if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or x<0 for x in self.durations) or not self.assumptions:raise ValueError("trace requires nonnegative durations and labeled assumptions")
@dataclass(frozen=True)
class SimulationMetric:
 throughput:float; mean_latency:float; fairness:float; utilization:float
 def __post_init__(self):
  if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or x<0 for x in (self.throughput,self.mean_latency,self.fairness,self.utilization)) or self.fairness>1 or self.utilization>1:raise ValueError("invalid simulation metric")
@dataclass(frozen=True)
class SchedulingSimulation:
 policy:str; trace:WorkloadTrace; metric:SimulationMetric; authoritative:bool=False
 def __post_init__(self):
  if self.authoritative:raise ValueError("simulation can never be authoritative")
def simulate(trace:WorkloadTrace,policy:str,worker_count:int):
 if isinstance(worker_count,bool) or not isinstance(worker_count,int) or worker_count<=0 or not policy:raise ValueError("worker_count and policy required")
 ds=trace.durations
 if not ds:return SchedulingSimulation(policy,trace,SimulationMetric(0,0,1,0))
 total=sum(ds); horizon=max(ds) if worker_count>=len(ds) else total/worker_count
 throughput=len(ds)/horizon if horizon else float(len(ds))
 mean=total/len(ds)
 fairness=1 if not ds else (sum(ds)**2)/(len(ds)*sum(x*x for x in ds)) if any(ds) else 1
 utilization=min(1,total/(max(horizon,1e-12)*worker_count))
 return SchedulingSimulation(policy,trace,SimulationMetric(throughput,mean,fairness,utilization))
