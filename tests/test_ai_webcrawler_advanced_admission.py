from skeleton.ai.webcrawler.core import CrawlEngine,CrawlPolicy,CrawlBudget,FetchResponse
def test_url_admission_rejects_pathological_dimensions():
 p=CrawlPolicy(max_url_length=80,max_query_pairs=2,max_path_segments=3)
 assert not p.admits("https://example.com/"+"x"*100)
 assert not p.admits("https://example.com/x?a=1&b=2&c=3")
 assert not p.admits("https://example.com/a/b/c/d")
 assert p.admits("https://example.com/a/b?a=1&b=2")
class Conditional:
 def __init__(self):self.headers=[]
 def fetch_once(self,url,**kw):
  self.headers.append(kw.get("extra_headers"))
  if len(self.headers)==1:return FetchResponse(url,200,{"content-type":"text/plain","etag":'"v1"'},b"User-agent: *\nAllow: /",0)
  return FetchResponse(url,304,{"etag":'"v1"'},b"",100)
 def fetch(self,url,**kw):return self.fetch_once(url,**kw)
def test_stale_robots_conditionally_revalidates_and_304_refreshes():
 f=Conditional();e=CrawlEngine(f,policy=CrawlPolicy(min_host_delay_seconds=0,robots_ttl_seconds=10),budget=CrawlBudget(max_requests=5))
 assert e.load_robots("https://example.com/x",now=0)
 assert e.load_robots("https://example.com/x",now=5)
 assert len(f.headers)==1
 assert e.load_robots("https://example.com/x",now=20)
 assert f.headers[-1]=={"If-None-Match":'"v1"'}
 assert e.robots.fresh("https://example.com/x",now=25,ttl=10)
