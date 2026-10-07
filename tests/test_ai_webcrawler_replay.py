import json
from skeleton.ai.webcrawler.core import CrawlEngine,CrawlPolicy,CrawlBudget,InMemoryCrawlStore,FetchResponse
class F:
 def fetch(self,url,**kwargs):return FetchResponse(url,200,{"content-type":"text/plain"},b"ok",1)
 fetch_once=fetch
def test_checkpoint_restore_preserves_frontier_identity_and_seen_state():
 s=InMemoryCrawlStore();e=CrawlEngine(F(),policy=CrawlPolicy(min_host_delay_seconds=0),store=s)
 e.install_robots("https://a.example","User-agent: *\nAllow: /")
 e.enqueue("https://a.example/a",priority=2);e.enqueue("https://a.example/b",priority=1)
 e.checkpoint("run");raw=s.load_checkpoint("run")
 restored=CrawlEngine.restore(F(),raw,policy=CrawlPolicy(min_host_delay_seconds=0),store=s)
 assert restored.checkpoint_state()==e.checkpoint_state()
def test_restore_rejects_unknown_checkpoint_schema():
 state=CrawlEngine(F()).checkpoint_state();state["schema"]="future.schema"
 try:CrawlEngine.restore(F(),state)
 except ValueError:pass
 else:raise AssertionError("unknown checkpoint schema accepted")
def test_restore_dedupes_frontier_urls_from_corrupt_duplicate_state():
 state=CrawlEngine(F()).checkpoint_state()
 item={"ready_at":0,"priority":0,"sequence":1,"url":"https://a.example/a","depth":0,"parent_url":None,"attempts":0}
 state["frontier"]=[item,dict(item,sequence=2)]
 try:CrawlEngine.restore(F(),state)
 except ValueError:pass
 else:raise AssertionError("duplicate frontier state accepted")
