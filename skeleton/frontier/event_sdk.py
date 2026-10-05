from dataclasses import dataclass
@dataclass(frozen=True)
class EventPublisher: schema:str; version:str
@dataclass(frozen=True)
class EventConsumer: consumer_id:str; accepted_schema:str; version:str
@dataclass(frozen=True)
class EventSDK:
 seen:frozenset[str]=frozenset()
 def envelope(self,p,event_id,payload):return {"id":event_id,"schema":p.schema,"version":p.version,"payload":payload}
 def consume(self,c,envelope):
  if (envelope["schema"],envelope["version"])!=(c.accepted_schema,c.version):raise ValueError("event schema drift")
  if envelope["id"] in self.seen:return self,False
  return EventSDK(self.seen|{envelope["id"]}),True
