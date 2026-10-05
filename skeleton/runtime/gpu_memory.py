from dataclasses import dataclass
@dataclass(frozen=True)
class GPUMemoryReservation: reservation_id:str; start:int; size:int
@dataclass(frozen=True)
class GPUAllocation: reservation:GPUMemoryReservation; committed:bool
@dataclass(frozen=True)
class GPUMemoryPool:
 capacity:int; reservations:tuple[GPUMemoryReservation,...]=()
 def __post_init__(self):
  if isinstance(self.capacity,bool) or not isinstance(self.capacity,int) or self.capacity<=0:raise ValueError("positive GPU capacity required")
  ids=[r.reservation_id for r in self.reservations]
  if len(ids)!=len(set(ids)):raise ValueError("duplicate reservation identity")
  used=sorted(self.reservations,key=lambda x:x.start)
  if any(not r.reservation_id or isinstance(r.start,bool) or isinstance(r.size,bool) or r.start<0 or r.size<=0 for r in used):raise ValueError("invalid reservation")
  if any(a.start+a.size>b.start for a,b in zip(used,used[1:])) or any(r.start+r.size>self.capacity for r in used):raise ValueError("overlapping/out-of-bounds reservation")
 def reserve(self,rid,size):
  if not rid or rid in {r.reservation_id for r in self.reservations}:raise ValueError("unique reservation id required")
  if isinstance(size,bool) or not isinstance(size,int) or size<=0:raise ValueError("invalid reservation size")
  used=sorted(self.reservations,key=lambda x:x.start);start=0
  for r in used:
   if r.start-start>=size:break
   start=max(start,r.start+r.size)
  if start+size>self.capacity:raise MemoryError("gpu memory unavailable")
  r=GPUMemoryReservation(rid,start,size);return GPUMemoryPool(self.capacity,self.reservations+(r,)),r
 def release(self,rid):
  if rid not in {r.reservation_id for r in self.reservations}:raise KeyError("unknown reservation")
  return GPUMemoryPool(self.capacity,tuple(r for r in self.reservations if r.reservation_id!=rid))
