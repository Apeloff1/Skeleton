from dataclasses import dataclass
@dataclass(frozen=True)
class GPUMemoryReservation: reservation_id:str; start:int; size:int
@dataclass(frozen=True)
class GPUAllocation: reservation:GPUMemoryReservation; committed:bool
@dataclass(frozen=True)
class GPUMemoryPool:
 capacity:int; reservations:tuple[GPUMemoryReservation,...]=()
 def reserve(self,rid,size):
  if size<=0:raise ValueError("invalid reservation size")
  used=sorted(self.reservations,key=lambda x:x.start);start=0
  for r in used:
   if r.start-start>=size:break
   start=max(start,r.start+r.size)
  if start+size>self.capacity:raise MemoryError("gpu memory unavailable")
  r=GPUMemoryReservation(rid,start,size);return GPUMemoryPool(self.capacity,self.reservations+(r,)),r
