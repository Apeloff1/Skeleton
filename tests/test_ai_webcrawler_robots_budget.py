from skeleton.ai.webcrawler.core import CrawlEngine,CrawlPolicy,CrawlBudget,FetchResponse
class F:
 def __init__(self):self.n=0
 def fetch(self,url,**kw):
  self.n+=1
  if url.endswith("/robots.txt"):raise OSError("temporary")
  return FetchResponse(url,200,{"content-type":"text/plain"},b"x",0)
def test_transient_robots_failure_does_not_permanently_mark_url_seen():
 f=F();e=CrawlEngine(f,policy=CrawlPolicy(retry_base_seconds=1),budget=CrawlBudget(max_requests=10))
 assert e.enqueue("https://a.example/x")
 assert e.step(now=0) is None
 assert "https://a.example/x" not in e._seen
 assert "https://a.example/x" in e._queued
def test_robots_request_consuming_last_budget_prevents_resource_fetch():
 class R:
  def __init__(self):self.urls=[]
  def fetch(self,url,**kw):
   self.urls.append(url);return FetchResponse(url,404,{"content-type":"text/plain"},b"",0)
 r=R();e=CrawlEngine(r,budget=CrawlBudget(max_requests=1));e.enqueue("https://a.example/x")
 assert e.step(now=0) is None
 assert r.urls==["https://a.example/robots.txt"]

class HopRobots:
 def __init__(self,rows):self.rows=rows;self.calls=[]
 def fetch_once(self,url,**kw):self.calls.append(url);return self.rows[url]
 def fetch(self,url,**kw):return self.fetch_once(url,**kw)
def test_robots_redirects_charge_each_hop_and_install_origin_policy():
 rows={
  "https://a.example/robots.txt":FetchResponse("https://a.example/robots.txt",302,{"location":"https://cdn.example/r.txt"},b"",0),
  "https://cdn.example/r.txt":FetchResponse("https://cdn.example/r.txt",200,{"content-type":"text/plain"},b"User-agent: *\nAllow: /",0),
 }
 f=HopRobots(rows);e=CrawlEngine(f,policy=CrawlPolicy(min_host_delay_seconds=0),budget=CrawlBudget(max_requests=5))
 assert e.load_robots("https://a.example/x",now=0)
 assert e.robots.allowed("https://a.example/x")
 assert e.budget.requests==2 and f.calls==["https://a.example/robots.txt","https://cdn.example/r.txt"]
def test_robots_redirect_obeys_destination_host_pacing():
 rows={"https://a.example/robots.txt":FetchResponse("https://a.example/robots.txt",302,{"location":"https://b.example/r"},b"",0)}
 f=HopRobots(rows);e=CrawlEngine(f,policy=CrawlPolicy(min_host_delay_seconds=0));e._host_ready["b.example"]=5
 assert not e.load_robots("https://a.example/x",now=0)
 assert f.calls==["https://a.example/robots.txt"]
