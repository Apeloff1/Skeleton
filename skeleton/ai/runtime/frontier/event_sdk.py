from dataclasses import dataclass
@dataclass(frozen=True)
class EventPublisher: schema:str; version:str
@dataclass(frozen=True)
class EventConsumer: consumer_id:str; accepted_schema:str; version:str
@dataclass(frozen=True)
class EventSDK:
 seen:frozenset[str]=frozenset()
 def envelope(self,p,event_id,payload):
  if not event_id or not p.schema or not p.version:raise ValueError("event identity/schema/version required")
  return {"id":event_id,"schema":p.schema,"version":p.version,"payload":payload}
 def consume(self,c,envelope):
  if not c.consumer_id or not isinstance(envelope,dict) or not {"id","schema","version","payload"}.issubset(envelope):raise ValueError("malformed event envelope")
  if (envelope["schema"],envelope["version"])!=(c.accepted_schema,c.version):raise ValueError("event schema drift")
  if envelope["id"] in self.seen:return self,False
  return EventSDK(self.seen|{envelope["id"]}),True
