from skeleton.ai.webcrawler.core import CrawlEngine,CrawlPolicy,FetchResponse
from skeleton.ai.webcrawler.redirects import fetch_with_policy,RedirectPolicyError
class HopFetcher:
 def __init__(self,rows):self.rows=rows;self.calls=[]
 def fetch_once(self,url,**kwargs):
  self.calls.append(url);return self.rows[url]
 def fetch(self,url,**kwargs):return self.fetch_once(url,**kwargs)
def r(url,status,location=None,body=b"ok"):
 h={"content-type":"text/plain"}
 if location:h["location"]=location
 return FetchResponse(url,status,h,body,1)
def test_cross_origin_redirect_loads_and_checks_destination_robots_first():
 rows={
  "https://a.example/start":r("https://a.example/start",302,"https://b.example/final",b""),
  "https://b.example/robots.txt":r("https://b.example/robots.txt",200,body=b"User-agent: *\nDisallow: /final"),
  "https://b.example/final":r("https://b.example/final",200),
 }
 f=HopFetcher(rows);e=CrawlEngine(f,policy=CrawlPolicy(min_host_delay_seconds=0))
 e.install_robots("https://a.example","User-agent: *\nAllow: /")
 try:fetch_with_policy(e,"https://a.example/start",now=0)
 except RedirectPolicyError:pass
 else:raise AssertionError("robots-denied redirect followed")
 assert f.calls==["https://a.example/start","https://b.example/robots.txt"]
def test_redirect_loop_is_rejected():
 rows={"https://a.example/a":r("https://a.example/a",302,"/b",b""),"https://a.example/b":r("https://a.example/b",302,"/a",b"")}
 f=HopFetcher(rows);e=CrawlEngine(f,policy=CrawlPolicy(min_host_delay_seconds=0))
 e.install_robots("https://a.example","User-agent: *\nAllow: /")
 try:fetch_with_policy(e,"https://a.example/a",now=0)
 except RedirectPolicyError:pass
 else:raise AssertionError("redirect loop accepted")
 assert f.calls==["https://a.example/a","https://a.example/b"]
