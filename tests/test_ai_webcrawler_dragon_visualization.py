from dataclasses import dataclass
from skeleton.ai.webcrawler.dragon_events import DragonEventStream
from skeleton.ai.webcrawler.dragon_visual_state import visual_state
from skeleton.ai.webcrawler.dragon_observer import DragonCrawlObserver
from skeleton.ai.webcrawler.dragon_graph import CrawlGraphProjection
@dataclass(frozen=True)
class Chunk:chunk_id:str
@dataclass(frozen=True)
class Doc:
 canonical_url:str="https://example.com/a";content_hash:str="hash";text:str="hello";links:tuple=();source_score:float=.8
def test_fire_only_occurs_after_acceptance_when_observer_used_in_order():
 s=DragonEventStream();o=DragonCrawlObserver(s);d=Doc()
 o.discovered(d.canonical_url,at=1,depth=1,parent="https://example.com/");o.accepted(d,at=2);o.burn(d,(Chunk("c1"),Chunk("c2")),at=3)
 kinds=[x.kind for x in s.events];assert kinds==["frontier_discovered","acquisition_accepted","burn_started","burn_chunk","burn_chunk","burn_complete"]
 assert visual_state(s.events[-1]).label=="Extraction complete"
 assert visual_state(s.events[-1]).progress==1.0
 # A completed burn event alone does not certify a separate index write.
def test_graph_projection_tracks_real_event_state():
 s=DragonEventStream();g=CrawlGraphProjection()
 for e in (s.emit("frontier_discovered","https://x/a",at=1,payload={"depth":1,"parent":"https://x/"}),s.emit("fetch_started","https://x/a",at=2),s.emit("policy_rejected","https://x/a",at=3,payload={"reason":"robots"})):g.apply(e)
 nodes,edges=g.snapshot();assert nodes[0].state=="rejected" and edges[0].parent=="https://x/"
def test_event_ids_are_deterministic():
 a=DragonEventStream().emit("visual_probe","https://x",at=1,payload={"region":"hero"})
 b=DragonEventStream().emit("visual_probe","https://x",at=1,payload={"region":"hero"})
 assert a.event_id==b.event_id
