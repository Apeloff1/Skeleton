"""Crawler-controlled redirect traversal with policy, budget and robots checks at every hop."""
from __future__ import annotations
from urllib.parse import urljoin,urlsplit
from .core import canonicalize_url
class RedirectPolicyError(ValueError):pass
class RedirectFetchError(RuntimeError):
    def __init__(self,message,*,request_started=False):super().__init__(message);self.request_started=request_started
def fetch_with_policy(engine,url,*,now):
    current=canonicalize_url(url);seen=set()
    for hop in range(engine.policy.max_redirects+1):
        if current in seen:raise RedirectPolicyError("redirect loop")
        seen.add(current)
        if not engine.policy.admits(current):raise RedirectPolicyError("redirect destination rejected by crawl policy")
        if not engine.robots.known(current) and not engine.load_robots(current,now=now):
            raise RedirectPolicyError("redirect destination robots unavailable")
        if not engine.budget.can_request():raise RedirectPolicyError("crawl request budget exhausted")
        if not engine.robots.allowed(current):raise RedirectPolicyError("redirect destination denied by robots")
        host=urlsplit(current).hostname or ""
        ready=engine._host_ready.get(host,0.0)
        if ready>now:raise RedirectPolicyError("redirect destination host is not ready")
        delay=max(engine.policy.min_host_delay_seconds,engine.robots.crawl_delay(current) or 0.0)
        engine._host_ready[host]=now+delay
        fetch_once=getattr(engine.fetcher,"fetch_once",None)
        if fetch_once is None:
            if hop:raise RedirectPolicyError("fetcher cannot expose redirect hops")
            response=engine.fetcher.fetch(current,user_agent=engine.policy.user_agent,max_bytes=engine.policy.max_response_bytes)
        else:
            try:response=fetch_once(current,user_agent=engine.policy.user_agent,max_bytes=engine.policy.max_response_bytes)
            except Exception as exc:raise RedirectFetchError("redirect hop fetch failed",request_started=True) from exc
        body=response.body[:engine.policy.max_response_bytes]
        engine.budget.charge_response(len(body),accepted=False)
        if response.status not in {301,302,303,307,308}:return response
        location=response.headers.get("location")
        if not location or hop>=engine.policy.max_redirects:raise RedirectPolicyError("redirect limit or malformed redirect")
        current=canonicalize_url(urljoin(current,location))
    raise RedirectPolicyError("redirect limit exceeded")

def fetch_robots_with_policy(engine,url,*,now):
    """Fetch robots without recursively requiring robots authorization."""
    current=canonicalize_url(url);seen=set();limit=min(engine.policy.max_response_bytes,512_000)
    for hop in range(engine.policy.max_redirects+1):
        if current in seen:raise RedirectPolicyError("robots redirect loop")
        seen.add(current)
        if not engine.policy.admits(current):raise RedirectPolicyError("robots redirect destination rejected")
        if not engine.budget.can_request():raise RedirectPolicyError("crawl request budget exhausted")
        host=urlsplit(current).hostname or ""
        if engine._host_ready.get(host,0.0)>now:raise RedirectPolicyError("robots redirect destination host is not ready")
        engine._host_ready[host]=now+engine.policy.min_host_delay_seconds
        fetch_once=getattr(engine.fetcher,"fetch_once",None)
        try:
            response=(fetch_once(current,user_agent=engine.policy.user_agent,max_bytes=limit)
                      if fetch_once else engine.fetcher.fetch(current,user_agent=engine.policy.user_agent,max_bytes=limit))
        except Exception as exc:
            engine.budget.requests+=1
            raise RedirectFetchError("robots redirect hop fetch failed",request_started=True) from exc
        body=response.body[:limit];engine.budget.charge_response(len(body),accepted=False)
        if response.status not in {301,302,303,307,308}:return response
        location=response.headers.get("location")
        if not location or hop>=engine.policy.max_redirects:raise RedirectPolicyError("robots redirect limit or malformed redirect")
        current=canonicalize_url(urljoin(current,location))
    raise RedirectPolicyError("robots redirect limit exceeded")
